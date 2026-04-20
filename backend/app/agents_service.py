from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import unicodedata
import re
from threading import Lock
from typing import Any, Callable
from uuid import uuid4

from fastapi import HTTPException, status

from .agents_catalog import load_agent_definitions
from .agents_mcp_bridge import call_mcp_tool
from .agents_providers import get_provider_client
from .agents_schemas import (
    AgentChatRequest,
    AgentChatResponse,
    AgentChatTurn,
    AgentConversation,
    AgentDefinition,
    AgentHandoffRequest,
    AgentMessage,
)
from .drug_sources import get_grounded_medication_context
from .schemas import UserRecord
from .tiers import TIER_FEATURES


class AgentsService:
    def __init__(self) -> None:
        self._definitions = {item.id: item for item in load_agent_definitions() if item.enabled}
        self._conversations: dict[str, AgentConversation] = {}
        self._tool_history: dict[str, list[str]] = {}
        self._lock = Lock()

    def list_agents(self) -> list[AgentDefinition]:
        return list(self._definitions.values())

    def list_agents_for_user(self, *, user: UserRecord) -> list[AgentDefinition]:
        allowed = set(TIER_FEATURES[user.tier]["allowed_agents"])
        return [
            agent for agent in self._definitions.values() if any(tag in allowed for tag in agent.style_tags)
        ]

    def get_agent(self, agent_id: str) -> AgentDefinition:
        agent = self._definitions.get(agent_id)
        if agent is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
        return agent

    def get_agent_for_user(self, *, user: UserRecord, agent_id: str) -> AgentDefinition:
        agent = self.get_agent(agent_id)
        allowed = TIER_FEATURES[user.tier]["allowed_agents"]
        if not any(tag in allowed for tag in agent.style_tags):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Agent '{agent_id}' is not available for the user's tier",
            )
        return agent

    async def chat_with_agent(
        self,
        *,
        user: UserRecord,
        agent_id: str,
        payload: AgentChatRequest,
        on_tool_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> AgentChatResponse:
        chain = [agent_id] + [item for item in payload.handoff_to if item and item != agent_id]
        return await self._chat_with_chain(user=user, payload=payload, chain=chain, on_tool_event=on_tool_event)

    async def chat_with_orchestrator(
        self,
        *,
        user: UserRecord,
        payload: AgentChatRequest,
        on_tool_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> AgentChatResponse:
        chain = self._build_orchestration_chain(user=user, payload=payload)
        return await self._chat_with_chain(user=user, payload=payload, chain=chain, on_tool_event=on_tool_event)

    def _build_orchestration_chain(self, *, user: UserRecord, payload: AgentChatRequest) -> list[str]:
        available_agents = [agent.id for agent in self.list_agents_for_user(user=user)]
        if not available_agents:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No agents available for the user's tier")

        message = payload.message.lower()
        metadata = payload.metadata if isinstance(payload.metadata, dict) else {}
        has_med_context = bool(metadata.get("current_medications") or metadata.get("patient_context"))
        wants_safety = any(
            keyword in message
            for keyword in [
                "interaction",
                "interactions",
                "contraind",
                "side effect",
                "adverse",
                "risk",
                "safe",
                "sigur",
                "contraindic",
                "efecte adverse",
            ]
        )
        wants_patient_friendly = any(
            keyword in message
            for keyword in [
                "simple",
                "plain",
                "for patient",
                "layman",
                "romanian",
                "romaneste",
                "explica",
                "pe inteles",
            ]
        )

        chain: list[str] = []

        def _add(agent_id: str) -> None:
            if agent_id in available_agents and agent_id not in chain:
                chain.append(agent_id)

        _add("medication-info-agent")
        if wants_safety or has_med_context:
            _add("safety-contraindication-agent")
        if wants_patient_friendly or "safety-contraindication-agent" in chain:
            _add("layman-translator-agent")

        if not chain:
            chain = [available_agents[0]]

        return chain

    async def _chat_with_chain(
        self,
        *,
        user: UserRecord,
        payload: AgentChatRequest,
        chain: list[str],
        on_tool_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> AgentChatResponse:
        if not chain:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Agent chain cannot be empty")

        first_agent = self.get_agent_for_user(user=user, agent_id=chain[0])
        conversation = self._get_or_create_conversation(payload.conversation_id, participants=[first_agent.id, user.id, *chain])

        grounded_context = await self._build_grounding_context(payload)

        self._append_message(
            conversation.conversation_id,
            AgentMessage(
                role="user",
                content=payload.message,
                sender=user.id,
                timestamp=_utcnow(),
            ),
        )

        turns: list[AgentChatTurn] = []
        current_input = payload.message
        conversation_tool_history = list(self._tool_history.get(conversation.conversation_id, []))

        for idx, next_agent_id in enumerate(chain):
            current_agent = self.get_agent_for_user(user=user, agent_id=next_agent_id)
            if idx > 0:
                self._append_message(
                    conversation.conversation_id,
                    AgentMessage(
                        role="agent",
                        content=current_input,
                        sender=chain[idx - 1],
                        timestamp=_utcnow(),
                    ),
                )

            mcp_tool_calls = await self._run_agent_mcp_tools(
                agent_id=current_agent.id,
                grounded_context=grounded_context,
                user_id=user.id,
                on_tool_call=(
                    (lambda call, idx=idx, aid=current_agent.id: on_tool_event({"turn_index": idx, "agent_id": aid, "call": call}))
                    if on_tool_event
                    else None
                ),
            )

            compact_rows = self._compact_tool_history_rows(mcp_tool_calls)
            if compact_rows:
                conversation_tool_history.extend(compact_rows)
                conversation_tool_history = conversation_tool_history[-60:]
                self._tool_history[conversation.conversation_id] = list(conversation_tool_history)

            agent_grounded_context = {
                **grounded_context,
                "mcp_tool_calls": mcp_tool_calls,
                "mcp_tool_history": conversation_tool_history[-20:],
            }

            response = await self._invoke_agent(
                agent=current_agent,
                conversation_id=conversation.conversation_id,
                grounded_context=agent_grounded_context,
            )

            thought_summary = self._build_thought_summary(
                agent_id=current_agent.id,
                grounded_context=grounded_context,
                mcp_tool_calls=mcp_tool_calls,
            )

            clinician_summary, patient_summary = self._split_outputs(
                response=response,
                agent_id=current_agent.id,
                grounded_context=agent_grounded_context,
            )

            self._append_message(
                conversation.conversation_id,
                AgentMessage(
                    role="assistant",
                    content=response,
                    sender=current_agent.id,
                    timestamp=_utcnow(),
                ),
            )

            turns.append(
                AgentChatTurn(
                    agent_id=current_agent.id,
                    response=response,
                    provider=current_agent.provider,
                    model=current_agent.model,
                    thought_summary=thought_summary,
                    mcp_tool_calls=mcp_tool_calls,
                    clinician_summary=clinician_summary,
                    patient_summary=patient_summary,
                    evidence_snippets=agent_grounded_context["evidence_snippets"],
                    source_links=agent_grounded_context["source_links"],
                )
            )
            current_input = response

        final_turn = turns[-1]
        return AgentChatResponse(
            conversation_id=conversation.conversation_id,
            final_agent_id=final_turn.agent_id,
            final_response=final_turn.response,
            clinician_summary=final_turn.clinician_summary or final_turn.response,
            patient_summary=final_turn.patient_summary or final_turn.response,
            evidence_snippets=final_turn.evidence_snippets,
            source_links=final_turn.source_links,
            turns=turns,
        )

    async def handoff(self, *, user: UserRecord, payload: AgentHandoffRequest) -> AgentChatResponse:
        from_agent = self.get_agent_for_user(user=user, agent_id=payload.from_agent_id)
        to_agent = self.get_agent_for_user(user=user, agent_id=payload.to_agent_id)
        conversation = self._get_or_create_conversation(
            payload.conversation_id,
            participants=[from_agent.id, to_agent.id, user.id],
        )

        grounded_context = await self._build_grounding_context(
            AgentChatRequest(
                message=payload.message,
                conversation_id=payload.conversation_id,
                metadata=payload.metadata,
            )
        )

        self._append_message(
            conversation.conversation_id,
            AgentMessage(
                role="agent",
                content=payload.message,
                sender=from_agent.id,
                timestamp=_utcnow(),
            ),
        )

        mcp_tool_calls = await self._run_agent_mcp_tools(
            agent_id=to_agent.id,
            grounded_context=grounded_context,
            user_id=user.id,
        )
        conversation_tool_history = list(self._tool_history.get(conversation.conversation_id, []))
        compact_rows = self._compact_tool_history_rows(mcp_tool_calls)
        if compact_rows:
            conversation_tool_history.extend(compact_rows)
            conversation_tool_history = conversation_tool_history[-60:]
            self._tool_history[conversation.conversation_id] = list(conversation_tool_history)
        agent_grounded_context = {
            **grounded_context,
            "mcp_tool_calls": mcp_tool_calls,
            "mcp_tool_history": conversation_tool_history[-20:],
        }
        response = await self._invoke_agent(
            agent=to_agent,
            conversation_id=conversation.conversation_id,
            grounded_context=agent_grounded_context,
        )
        thought_summary = self._build_thought_summary(
            agent_id=to_agent.id,
            grounded_context=agent_grounded_context,
            mcp_tool_calls=mcp_tool_calls,
        )
        clinician_summary, patient_summary = self._split_outputs(
            response=response,
            agent_id=to_agent.id,
            grounded_context=agent_grounded_context,
        )
        self._append_message(
            conversation.conversation_id,
            AgentMessage(
                role="assistant",
                content=response,
                sender=to_agent.id,
                timestamp=_utcnow(),
            ),
        )

        return AgentChatResponse(
            conversation_id=conversation.conversation_id,
            final_agent_id=to_agent.id,
            final_response=response,
            clinician_summary=clinician_summary,
            patient_summary=patient_summary,
            evidence_snippets=grounded_context["evidence_snippets"],
            source_links=grounded_context["source_links"],
            turns=[
                AgentChatTurn(
                    agent_id=to_agent.id,
                    response=response,
                    provider=to_agent.provider,
                    model=to_agent.model,
                    thought_summary=thought_summary,
                    mcp_tool_calls=mcp_tool_calls,
                    clinician_summary=clinician_summary,
                    patient_summary=patient_summary,
                    evidence_snippets=agent_grounded_context["evidence_snippets"],
                    source_links=agent_grounded_context["source_links"],
                )
            ],
        )

    def get_conversation(self, conversation_id: str) -> AgentConversation:
        conversation = self._conversations.get(conversation_id)
        if conversation is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
        return conversation

    async def _invoke_agent(self, *, agent: AgentDefinition, conversation_id: str, grounded_context: dict[str, Any]) -> str:
        provider_client = get_provider_client(agent.provider)
        messages = self._build_messages(
            agent=agent,
            conversation_id=conversation_id,
            grounded_context=grounded_context,
        )
        response = await provider_client.generate(agent, messages)
        if not self._is_empty_provider_response(response):
            return response

        retry_context = {
            **grounded_context,
            "mcp_tool_calls": [],
            "mcp_tool_history": list(grounded_context.get("mcp_tool_history", []))[-12:],
            "forced_synthesis_prompt": self._build_forced_synthesis_prompt(grounded_context),
        }
        retry_messages = self._build_messages(
            agent=agent,
            conversation_id=conversation_id,
            grounded_context=retry_context,
        )
        retry_response = await provider_client.generate(agent, retry_messages)
        if not self._is_empty_provider_response(retry_response):
            return retry_response

        return self._build_fallback_response(
            agent_id=agent.id,
            grounded_context=grounded_context,
            mcp_tool_calls=list(grounded_context.get("mcp_tool_calls", [])),
        )

    def _build_messages(
        self,
        *,
        agent: AgentDefinition,
        conversation_id: str,
        grounded_context: dict[str, Any],
    ) -> list[dict[str, str]]:
        conversation = self.get_conversation(conversation_id)
        window = conversation.messages[-20:]
        payload: list[dict[str, str]] = [
            {
                "role": "system",
                "content": (
                    agent.system_prompt
                    + "\n\nAlways stay grounded in the provided evidence context."
                ),
            }
        ]

        evidence_lines = grounded_context.get("evidence_snippets", [])
        source_links = grounded_context.get("source_links", [])
        if evidence_lines:
            payload.append(
                {
                    "role": "user",
                    "content": (
                        "Evidence context:\n"
                        + "\n".join([f"- {line}" for line in evidence_lines[:8]])
                        + ("\nSources:\n" + "\n".join(source_links) if source_links else "")
                    ),
                }
            )

        tool_history = grounded_context.get("mcp_tool_history", [])
        if isinstance(tool_history, list) and tool_history:
            payload.append(
                {
                    "role": "user",
                    "content": "MCP call history (compact):\n" + "\n".join([f"- {line}" for line in tool_history[-20:]]),
                }
            )

        forced_synthesis_prompt = grounded_context.get("forced_synthesis_prompt")
        if isinstance(forced_synthesis_prompt, str) and forced_synthesis_prompt.strip():
            payload.append(
                {
                    "role": "user",
                    "content": forced_synthesis_prompt.strip(),
                }
            )

        for item in window:
            if item.role == "assistant":
                role = "assistant"
            else:
                role = "user"
            sender = f" ({item.sender})" if item.sender else ""
            payload.append(
                {
                    "role": role,
                    "content": f"[{item.role}{sender}] {item.content}",
                }
            )

        if not payload:
            payload.append({"role": "user", "content": "No conversation history."})

        return payload

    def _build_fallback_response(
        self,
        *,
        agent_id: str,
        grounded_context: dict[str, Any],
        mcp_tool_calls: list[dict[str, Any]],
    ) -> str:
        snippets = grounded_context.get("evidence_snippets", []) if isinstance(grounded_context, dict) else []
        lines: list[str] = ["Grounded summary from retrieved MCP evidence:"]

        if snippets:
            lines.append("Evidence snippets:")
            lines.extend([f"- {item}" for item in snippets[:6]])

        facts_sources: list[str] = []
        facts_highlights: list[str] = []
        for call in mcp_tool_calls:
            if not isinstance(call, dict):
                continue
            if call.get("tool_name") != "search_medication_facts":
                continue
            output = call.get("output")
            if not isinstance(output, dict):
                continue
            data = output.get("data")
            if not isinstance(data, dict):
                continue
            source = str(data.get("source") or "").strip().lower()
            if source:
                facts_sources.append(source)
            canonical = str(data.get("canonical_name") or "").strip()
            if canonical:
                facts_highlights.append(f"canonical_name={canonical}")

        if facts_highlights:
            lines.append("Medication facts retrieved:")
            lines.extend([f"- {item}" for item in facts_highlights[:5]])

        if facts_sources:
            uniq_sources = ", ".join(sorted(list(dict.fromkeys(facts_sources))))
            lines.append(f"Sources observed: {uniq_sources}")

        lines.append(f"Agent: {agent_id}")
        return "\n".join(lines)

    @staticmethod
    def _is_empty_provider_response(response: str) -> bool:
        return response.strip() in {
            "",
            "No content returned by Gemini provider.",
            "No content returned by API agent provider.",
        }

    def _build_forced_synthesis_prompt(self, grounded_context: dict[str, Any]) -> str:
        history = grounded_context.get("mcp_tool_history", [])
        rows = [str(item).strip() for item in history if str(item).strip()]
        if not rows:
            return "Provide a concise grounded answer using available evidence only."

        return (
            "Synthesize a natural clinician-style answer using only these compact MCP results. "
            "Do not add external knowledge. If data is missing, state uncertainty.\n"
            + "\n".join([f"- {item}" for item in rows[-12:]])
        )

    def _compact_tool_history_rows(self, tool_calls: list[dict[str, Any]]) -> list[str]:
        rows: list[str] = []
        for call in tool_calls:
            if not isinstance(call, dict):
                continue
            row = self._compact_tool_call_row(call)
            if row:
                rows.append(row)
        return rows

    def _compact_tool_call_row(self, call: dict[str, Any]) -> str:
        tool_name = str(call.get("tool_name") or "unknown_tool")
        tool_input = call.get("input")
        query = ""
        if isinstance(tool_input, dict):
            for key in ["name", "medication_name", "drug_id", "caller_id"]:
                value = tool_input.get(key)
                if isinstance(value, str) and value.strip():
                    query = value.strip()
                    break

        output = call.get("output")
        if isinstance(output, dict):
            ok = output.get("ok")
            data = output.get("data") if isinstance(output.get("data"), dict) else {}
            error = output.get("error") if isinstance(output.get("error"), dict) else {}
            if ok is False:
                code = str(error.get("code") or "ERROR")
                message = str(error.get("message") or "tool call failed").strip()
                return f"{tool_name} | query={query} | result={code}: {message[:180]}"

            source = str(data.get("source") or "").strip()
            canonical = str(data.get("canonical_name") or "").strip()
            indications = data.get("indications") if isinstance(data.get("indications"), list) else []
            indication_count = len(indications)
            result_bits = [item for item in [source, canonical] if item]
            if indication_count:
                result_bits.append(f"indications={indication_count}")
            result_text = " | ".join(result_bits) if result_bits else "ok"
            return f"{tool_name} | query={query} | result={result_text[:220]}"

        status = str(call.get("status") or "unknown")
        return f"{tool_name} | query={query} | result={status}"

    async def _build_grounding_context(self, payload: AgentChatRequest) -> dict[str, Any]:
        raw_name = str(payload.metadata.get("medication_name", "")).strip()
        if not raw_name:
            raw_name = self._extract_medication_guess(payload.message)

        if not raw_name:
            return {"evidence_snippets": [], "source_links": [], "metadata": payload.metadata}

        candidates = self._medication_query_candidates(raw_name)
        grounded = await get_grounded_medication_context(candidates[0])
        selected_query = candidates[0]
        if not self._grounding_has_signal(grounded):
            for candidate in candidates[1:]:
                trial = await get_grounded_medication_context(candidate)
                if self._grounding_has_signal(trial):
                    grounded = trial
                    selected_query = candidate
                    break

        grounded["original_query"] = raw_name
        grounded["selected_query"] = selected_query
        grounded["query_candidates"] = candidates
        grounded["metadata"] = payload.metadata
        return grounded

    def _grounding_has_signal(self, grounded: dict[str, Any]) -> bool:
        if grounded.get("evidence_snippets"):
            return True
        rxnorm = grounded.get("rxnorm", {}) if isinstance(grounded.get("rxnorm"), dict) else {}
        if rxnorm.get("rxcui"):
            return True
        dailymed = grounded.get("dailymed", {}) if isinstance(grounded.get("dailymed"), dict) else {}
        if dailymed.get("spl_set_id"):
            return True
        return False

    def _medication_query_candidates(self, raw_name: str) -> list[str]:
        base = raw_name.strip()
        if not base:
            return []

        # DailyMed canonical names may contain vendor/formulation noise that harms retrieval.
        compact_base = re.sub(r"\[[^\]]*\]", " ", base)
        compact_base = re.sub(r"[(),]", " ", compact_base)
        compact_base = " ".join(compact_base.split()).strip()

        lowered = base.lower()
        compact_lowered = compact_base.lower()
        ascii_lowered = unicodedata.normalize("NFKD", lowered).encode("ascii", "ignore").decode("ascii")
        ascii_compact = unicodedata.normalize("NFKD", compact_lowered).encode("ascii", "ignore").decode("ascii")
        common_salt_tokens = {
            "sodium",
            "sodic",
            "potassium",
            "calcium",
            "hydrochloride",
            "hcl",
            "de",
            "sodiu",
        }
        noise_tokens = {
            "tablet",
            "capsule",
            "powder",
            "solution",
            "injection",
            "injectable",
            "monohydrate",
            "llc",
            "inc",
            "corp",
            "company",
            "pharmaceutical",
            "healthcare",
            "manufacturing",
        }

        variants = [
            base,
            lowered,
            ascii_lowered,
            compact_base,
            compact_lowered,
            ascii_compact,
            lowered.replace(" de sodiu", " sodium").replace(" sodic", " sodium"),
            ascii_lowered.replace(" de sodiu", " sodium").replace(" sodic", " sodium"),
            compact_lowered.replace(" de sodiu", " sodium").replace(" sodic", " sodium"),
            ascii_compact.replace(" de sodiu", " sodium").replace(" sodic", " sodium"),
            lowered.replace(" de sodiu", "").replace(" sodic", "").strip(),
            ascii_lowered.replace(" de sodiu", "").replace(" sodic", "").strip(),
            compact_lowered.replace(" de sodiu", "").replace(" sodic", "").strip(),
            ascii_compact.replace(" de sodiu", "").replace(" sodic", "").strip(),
        ]

        tokenized = [token for token in re.split(r"\s+", ascii_lowered) if token]
        without_salts = [token for token in tokenized if token not in common_salt_tokens]
        if without_salts:
            variants.append(" ".join(without_salts))

        compact_tokenized = [token for token in re.split(r"\s+", ascii_compact) if token]
        compact_without_noise = [
            token for token in compact_tokenized if token not in common_salt_tokens and token not in noise_tokens
        ]
        if compact_without_noise:
            variants.append(" ".join(compact_without_noise))
            variants.extend(compact_without_noise)

        # Small morphology fallback for close INN spelling variants (e.g. metamizol -> metamizole).
        if without_salts:
            head = without_salts[0]
            if head.endswith("ol") and not head.endswith("ole"):
                variants.append(" ".join([head + "e", *without_salts[1:]]).strip())
            if head.endswith("ole"):
                variants.append(" ".join([head[:-1], *without_salts[1:]]).strip())

        deduped: list[str] = []
        for item in variants:
            cleaned = " ".join(str(item).split()).strip()
            if cleaned and cleaned not in deduped:
                deduped.append(cleaned)
        return deduped or [base]

    def _extract_discovered_terms(self, call: dict[str, Any]) -> list[str]:
        output = call.get("output") if isinstance(call, dict) else None
        if not isinstance(output, dict):
            return []

        discovered: list[str] = []
        data = output.get("data")
        if isinstance(data, dict):
            for key in ["canonical_name", "matched_on"]:
                value = data.get(key)
                if isinstance(value, str) and value.strip():
                    discovered.append(value.strip())

            for key in ["aliases", "ingredients", "suggestions"]:
                values = data.get(key)
                if isinstance(values, list):
                    for item in values:
                        token = str(item).strip()
                        if token:
                            discovered.append(token)

        deduped: list[str] = []
        for item in discovered:
            if item not in deduped:
                deduped.append(item)
        return deduped

    def _extract_medication_guess(self, text: str) -> str:
        cleaned = text.strip()
        if not cleaned:
            return ""

        lowered = cleaned.lower()
        cutoff_keywords = [
            "interaction",
            "interactions",
            "interactiuni",
            "contraind",
            "side effect",
            "efecte adverse",
            "safety",
            "safe",
            "dosage",
            "doza",
        ]

        def _trim_intent_tail(value: str) -> str:
            trimmed = value
            for keyword in cutoff_keywords:
                idx = trimmed.find(keyword)
                if idx > 0:
                    trimmed = trimmed[:idx]
            trimmed = re.sub(r"\b(si|and|cu)\s*$", "", trimmed).strip()
            return trimmed.strip()

        patterns = [
            r"(?:ce\s+stii\s+despre|ce\s+stii\s+de|despre|about)\s+([a-z0-9\-\s]+)",
            r"(?:pentru|for)\s+([a-z0-9\-\s]+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, lowered)
            if not match:
                continue
            candidate = re.sub(r"[^a-z0-9\-\s]", " ", match.group(1)).strip()
            candidate = _trim_intent_tail(candidate)
            words = [part for part in candidate.split() if part]
            if words:
                return " ".join(words[:3])

        words = [part for part in re.sub(r"[^a-zA-Z0-9\-\s]", " ", cleaned).split() if part]
        stop_words = {
            "ce",
            "stii",
            "despre",
            "de",
            "the",
            "what",
            "about",
            "is",
            "are",
            "and",
            "for",
            "cu",
            "si",
        }
        filtered = [part for part in words if part.lower() not in stop_words]
        if not filtered:
            return ""
        return " ".join(filtered[:3])

    def _split_outputs(self, *, response: str, agent_id: str, grounded_context: dict[str, Any]) -> tuple[str, str]:
        if agent_id == "layman-translator-agent":
            return self._build_clinician_summary(response, grounded_context), response
        if agent_id == "safety-contraindication-agent":
            return response, self._build_patient_summary(response)
        if agent_id == "medication-info-agent":
            return response, self._build_patient_summary(response)
        return response, self._build_patient_summary(response)

    def _build_clinician_summary(self, response: str, grounded_context: dict[str, Any]) -> str:
        snippets = grounded_context.get("evidence_snippets", [])
        if not snippets:
            return response
        return response + "\n\nEvidence focus:\n" + "\n".join([f"- {item}" for item in snippets[:4]])

    def _build_patient_summary(self, response: str) -> str:
        return (
            "Patient-friendly summary: "
            + response[:900]
            + ("" if len(response) <= 900 else "...")
        )

    async def _run_agent_mcp_tools(
        self,
        *,
        agent_id: str,
        grounded_context: dict[str, Any],
        user_id: str,
        on_tool_call: Callable[[dict[str, Any]], None] | None = None,
    ) -> list[dict[str, Any]]:
        medication_name = str(grounded_context.get("canonical_name") or grounded_context.get("query") or "").strip()
        original_query = str(grounded_context.get("original_query") or "").strip()
        selected_query = str(grounded_context.get("selected_query") or "").strip()
        query_candidates = grounded_context.get("query_candidates", [])
        metadata = grounded_context.get("metadata", {})
        patient_context = metadata.get("patient_context", {}) if isinstance(metadata, dict) else {}
        current_medications = metadata.get("current_medications", []) if isinstance(metadata, dict) else []

        if not medication_name:
            return []

        calls: list[dict[str, Any]] = []

        async def _invoke(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
            call = call_mcp_tool(tool_name, args=args, caller_id=user_id)
            calls.append(call)
            if on_tool_call:
                on_tool_call(call)
                # Yield to event loop so stream clients receive tool events progressively.
                await asyncio.sleep(0)
            return call

        if agent_id == "medication-info-agent":
            seed_candidates = [selected_query, medication_name, original_query, *(query_candidates if isinstance(query_candidates, list) else [])]
            pending_terms: list[str] = []
            for candidate in seed_candidates:
                normalized = str(candidate).strip()
                if normalized and normalized not in pending_terms:
                    pending_terms.append(normalized)

            attempted_terms: list[str] = []
            attempted_facts_terms: set[str] = set()
            canonical_for_similar = medication_name
            found_openfda = False

            while pending_terms and len(attempted_terms) < 12:
                attempt_name = pending_terms.pop(0)
                if attempt_name in attempted_terms:
                    continue
                attempted_terms.append(attempt_name)

                normalize_call = await _invoke("normalize_medication_name", {"name": attempt_name})

                normalize_data = normalize_call.get("output", {}).get("data", {}) if isinstance(normalize_call.get("output"), dict) else {}
                canonical_from_call = normalize_data.get("canonical_name") if isinstance(normalize_data, dict) else None
                if isinstance(canonical_from_call, str) and canonical_from_call.strip():
                    canonical_for_similar = canonical_from_call.strip()

                facts_targets: list[str] = []
                for seed in [attempt_name, canonical_for_similar]:
                    for candidate in self._medication_query_candidates(str(seed or "")):
                        if candidate and candidate not in facts_targets:
                            facts_targets.append(candidate)

                facts_targets = [candidate for candidate in facts_targets if candidate not in attempted_facts_terms]

                if not facts_targets:
                    if attempt_name not in attempted_facts_terms:
                        facts_targets = [attempt_name]
                    else:
                        facts_targets = []

                facts_call: dict[str, Any] | None = None
                for facts_target in facts_targets[:6]:
                    attempted_facts_terms.add(facts_target)
                    trial_call = await _invoke("search_medication_facts", {"name": facts_target})
                    trial_data = trial_call.get("output", {}).get("data", {}) if isinstance(trial_call.get("output"), dict) else {}
                    trial_source = str(trial_data.get("source") or "").strip().lower() if isinstance(trial_data, dict) else ""

                    if facts_call is None and trial_call.get("status") == "success":
                        facts_call = trial_call

                    if trial_source == "openfda":
                        facts_call = trial_call
                        break

                if facts_call is None:
                    fallback_term = attempt_name
                    if fallback_term not in attempted_facts_terms:
                        attempted_facts_terms.add(fallback_term)
                        facts_call = await _invoke("search_medication_facts", {"name": fallback_term})
                    else:
                        facts_call = {
                            "tool_name": "search_medication_facts",
                            "status": "warning",
                            "output": {"ok": False, "data": {}, "error": {"code": "SKIPPED_DUPLICATE", "message": "Skipped duplicate facts query"}},
                        }

                if canonical_for_similar:
                    for candidate in self._medication_query_candidates(canonical_for_similar):
                        if candidate not in attempted_terms and candidate not in pending_terms:
                            pending_terms.insert(0, candidate)

                facts_data = facts_call.get("output", {}).get("data", {}) if isinstance(facts_call.get("output"), dict) else {}
                facts_source = str(facts_data.get("source") or "").strip().lower() if isinstance(facts_data, dict) else ""
                indications = facts_data.get("indications", []) if isinstance(facts_data, dict) else []
                evidence_rows = facts_data.get("evidence", []) if isinstance(facts_data, dict) else []
                has_signal = bool(indications)
                if not has_signal and isinstance(evidence_rows, list) and evidence_rows:
                    first_evidence = evidence_rows[0] if isinstance(evidence_rows[0], dict) else {}
                    snippets = first_evidence.get("snippets", []) if isinstance(first_evidence, dict) else []
                    has_signal = bool(snippets)
                if facts_source == "openfda":
                    found_openfda = True

                # Use response content to derive more specific follow-up queries.
                if isinstance(canonical_for_similar, str) and canonical_for_similar:
                    paren = re.findall(r"\(([^)]+)\)", canonical_for_similar)
                    ingredient_hint = paren[0].strip() if paren else ""
                    discovered_from_facts = [
                        canonical_for_similar,
                        ingredient_hint,
                        *(facts_data.get("ingredients", []) if isinstance(facts_data, dict) else []),
                        *(facts_data.get("aliases", []) if isinstance(facts_data, dict) else []),
                    ]
                    for discovered in discovered_from_facts:
                        for candidate in self._medication_query_candidates(str(discovered)):
                            if candidate not in attempted_terms and candidate not in pending_terms:
                                pending_terms.append(candidate)

                if facts_call.get("status") == "success" or normalize_call.get("status") == "success":
                    # Stop only after we have an openFDA-backed hit; DailyMed may seed follow-up terms.
                    if found_openfda and has_signal:
                        await _invoke("find_similar_medications", {"name": canonical_for_similar or attempt_name})
                        break
                    if found_openfda:
                        break

                discovered_terms = [
                    *self._extract_discovered_terms(normalize_call),
                    *self._extract_discovered_terms(facts_call),
                ]

                for discovered in discovered_terms:
                    for candidate in self._medication_query_candidates(discovered):
                        if candidate not in attempted_terms and candidate not in pending_terms:
                            pending_terms.append(candidate)
        elif agent_id == "layman-translator-agent":
            await _invoke(
                "explain_for_patient",
                {"medication_name": medication_name, "evidence_snippets": grounded_context.get("evidence_snippets", [])},
            )
        elif agent_id == "safety-contraindication-agent":
            await _invoke("collect_missing_context", {"patient_context": patient_context})
            await _invoke("check_contraindications", {"medication_name": medication_name, "patient_context": patient_context})
            await _invoke(
                "check_interactions",
                {
                    "medication_name": medication_name,
                    "current_medications": current_medications if isinstance(current_medications, list) else [],
                    "patient_context": patient_context,
                },
            )

        return calls

    def _build_thought_summary(
        self,
        *,
        agent_id: str,
        grounded_context: dict[str, Any],
        mcp_tool_calls: list[dict[str, Any]],
    ) -> str:
        success_count = len([item for item in mcp_tool_calls if item.get("status") == "success"])
        warning_count = len([item for item in mcp_tool_calls if item.get("status") == "warning"])
        evidence_count = len(grounded_context.get("evidence_snippets", []))
        return (
            f"{agent_id} used retrieval-first reasoning with {evidence_count} evidence snippet(s) "
            f"and {success_count}/{len(mcp_tool_calls)} MCP tool call(s) succeeded"
            + (f", {warning_count} returned warnings." if warning_count else ".")
        )

    def _get_or_create_conversation(self, conversation_id: str | None, *, participants: list[str]) -> AgentConversation:
        if conversation_id:
            existing = self._conversations.get(conversation_id)
            if existing is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
            return existing

        new_id = f"cnv-{uuid4().hex[:10]}"
        conversation = AgentConversation(
            conversation_id=new_id,
            participants=list(dict.fromkeys(participants)),
            messages=[],
        )
        with self._lock:
            self._conversations[new_id] = conversation
        return conversation

    def _append_message(self, conversation_id: str, message: AgentMessage) -> None:
        with self._lock:
            conversation = self._conversations.get(conversation_id)
            if conversation is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
            conversation.messages.append(message)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)
