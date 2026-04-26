from __future__ import annotations

import asyncio
import json
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
    AgentWorkEntry,
)
from .conversation_repository import ConversationRepository
from .drug_sources import get_grounded_medication_context
from .schemas import UserRecord
from .tiers import TIER_FEATURES


class AgentsService:
    def __init__(self, conversation_repository: ConversationRepository | None = None) -> None:
        self._definitions = {item.id: item for item in load_agent_definitions() if item.enabled}
        self._conversations: dict[str, AgentConversation] = {}
        self._tool_history: dict[str, list[str]] = {}
        self._tool_calls_by_message: dict[str, dict[str, list[dict[str, Any]]]] = {}
        self._stream_tasks: dict[str, tuple[str, asyncio.Task[None]]] = {}
        self._conversation_repository = conversation_repository
        self._lock = Lock()

        if self._conversation_repository is not None:
            for conversation in self._conversation_repository.list_conversations():
                self._conversations[conversation.conversation_id] = conversation

    def _has_recent_medication_flow(self, conversation: AgentConversation) -> bool:
        if not conversation.agent_work_history:
            return False
        last_entry = conversation.agent_work_history[-1]
        for turn in reversed(last_entry.turns or []):
            if turn.agent_id in {
                "medication-normalization-agent",
                "medication-evidence-gathering-agent",
                "medication-answer-synthesis-agent",
                "layman-translator-agent",
            }:
                return True
        return False

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
        conversation = self._get_or_create_conversation(
            payload.conversation_id,
            participants=["pharmacist-general-agent", user.id],
        )
        assistant_start_index = len([msg for msg in conversation.messages if msg.role == "assistant"])
        general_agent = self.get_agent_for_user(user=user, agent_id="pharmacist-general-agent")
        triage_prompt = (
            "Return INTENT_JSON on the first line with keys: intent (medication|general|unclear), "
            "confidence (0-1), rationale, medication_name (optional). Then a blank line, then RESPONSE. "
            "If intent is medication, still write a short acknowledgement in RESPONSE.\n\n"
            f"User message: {payload.message}"
        )
        conversation = self._get_or_create_conversation(
            payload.conversation_id,
            participants=[general_agent.id, user.id],
        )
        triage_response = await self._invoke_agent_with_history_prompt(
            agent=general_agent,
            conversation_id=conversation.conversation_id,
            prompt=triage_prompt,
        )
        triage_payload, general_response = self._extract_intent_payload(triage_response)
        intent = str(triage_payload.get("intent") or "").strip().lower()
        try:
            confidence = float(triage_payload.get("confidence", 0))
        except (TypeError, ValueError):
            confidence = 0.0
        medication_guess = self._extract_medication_guess(payload.message)
        follow_up_without_medication = (
            not medication_guess and self._has_recent_medication_flow(conversation)
        )
        should_call_med_analysis = not (intent == "general" and confidence >= 0.6)
        if follow_up_without_medication and intent == "medication":
            should_call_med_analysis = False

        triage_call = None
        if should_call_med_analysis:
            triage_call = call_mcp_tool(
                "medication_analysis",
                args={
                    "message": payload.message,
                    "triage_output": json.dumps(triage_payload, ensure_ascii=True),
                },
                caller_id=user.id,
            )
            triage_data = triage_call.get("output") if isinstance(triage_call, dict) else None
            tool_payload = triage_data.get("data", {}) if isinstance(triage_data, dict) else {}
            if isinstance(tool_payload, dict) and tool_payload:
                triage_payload = {**triage_payload, **tool_payload}

        trigger_medication_flow = bool(triage_payload.get("trigger_medication_flow"))
        if not should_call_med_analysis and intent == "general":
            trigger_medication_flow = False
        if follow_up_without_medication:
            trigger_medication_flow = False
        medication_name = str(triage_payload.get("medication_name") or "").strip()
        if trigger_medication_flow:
            general_response = "Starting medication analysis. I'll share results shortly."

        if on_tool_event:
            on_tool_event(
                {
                    "event_type": "step_started",
                    "turn_index": 0,
                    "agent_id": general_agent.id,
                    "stage_input": payload.message,
                    "message": f"Starting {general_agent.name}",
                }
            )
            if triage_call is not None:
                on_tool_event(
                    {
                        "event_type": "tool_call",
                        "turn_index": 0,
                        "agent_id": general_agent.id,
                        "call": triage_call,
                    }
                )
            on_tool_event(
                {
                    "event_type": "step_completed",
                    "turn_index": 0,
                    "agent_id": general_agent.id,
                    "stage_output": general_response or triage_response,
                    "next_stage_input": payload.message,
                    "message": f"Completed {general_agent.name}",
                }
            )

        triage_turn = AgentChatTurn(
            agent_id=general_agent.id,
            received_input=payload.message,
            response=general_response or triage_response,
            provider=general_agent.provider,
            model=general_agent.model,
            thought_summary=(
                "Intent triage via medication_analysis"
                if triage_call is not None
                else "Intent triage via general agent"
            ),
            mcp_tool_calls=[triage_call] if triage_call is not None else [],
            clinician_summary=general_response or triage_response,
            patient_summary=general_response or triage_response,
            evidence_snippets=[],
            source_links=[],
        )

        if trigger_medication_flow:
            if medication_name:
                payload.metadata = {
                    **(payload.metadata if isinstance(payload.metadata, dict) else {}),
                    "medication_name": medication_name,
                    "force_medication": True,
                }
            grounded_context = await self._build_grounding_context(payload)
            chain = [
                "medication-normalization-agent",
                "medication-evidence-gathering-agent",
                "medication-answer-synthesis-agent",
                "layman-translator-agent",
            ]
        else:
            grounded_context = {"evidence_snippets": [], "source_links": [], "metadata": payload.metadata}
            if not self._resolve_resume_anchor(conversation=conversation, user_id=user.id, payload=payload):
                self._append_message(
                    conversation.conversation_id,
                    AgentMessage(
                        role="user",
                        content=payload.message,
                        sender=user.id,
                        timestamp=_utcnow(),
                    ),
                )
            self._append_message(
                conversation.conversation_id,
                AgentMessage(
                    role="assistant",
                    content=general_response or triage_response,
                    sender=general_agent.id,
                    timestamp=_utcnow(),
                ),
            )
            self._record_agent_work(
                conversation_id=conversation.conversation_id,
                assistant_start_index=assistant_start_index,
                turns=[triage_turn],
            )
            return AgentChatResponse(
                conversation_id=conversation.conversation_id,
                final_agent_id=general_agent.id,
                final_response=general_response or triage_response,
                clinician_summary=general_response or triage_response,
                patient_summary=general_response or triage_response,
                evidence_snippets=[],
                source_links=[],
                turns=[triage_turn],
                agent_work_history=list(conversation.agent_work_history),
            )

        response = await self._chat_with_chain(
            user=user,
            payload=payload,
            chain=chain,
            on_tool_event=on_tool_event,
            grounded_context=grounded_context,
            turn_index_offset=1,
            record_agent_work=False,
        )
        response.turns.insert(0, triage_turn)
        self._record_agent_work(
            conversation_id=response.conversation_id,
            assistant_start_index=assistant_start_index,
            turns=response.turns,
        )
        response.agent_work_history = list(self.get_conversation(response.conversation_id).agent_work_history)
        return response

    def register_stream_task(self, *, request_id: str, user_id: str, task: asyncio.Task[None]) -> None:
        with self._lock:
            self._stream_tasks[request_id] = (user_id, task)

    def clear_stream_task(self, *, request_id: str) -> None:
        with self._lock:
            self._stream_tasks.pop(request_id, None)

    def cancel_stream_task(self, *, request_id: str, user_id: str) -> bool:
        with self._lock:
            item = self._stream_tasks.get(request_id)
        if not item:
            return False
        owner_id, task = item
        if owner_id != user_id:
            return False
        if not task.done():
            task.cancel()
        return True

    def _build_orchestration_chain(
        self,
        *,
        user: UserRecord,
        payload: AgentChatRequest,
        grounded_context: dict[str, Any],
    ) -> list[str]:
        available_agents = [agent.id for agent in self.list_agents_for_user(user=user)]
        if not available_agents:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No agents available for the user's tier")
        chain: list[str] = []

        def _add(agent_id: str) -> None:
            if agent_id in available_agents and agent_id not in chain:
                chain.append(agent_id)

        if not self._has_medication_intent(grounded_context):
            _add("pharmacist-general-agent")
        else:
            # Preferred explicit pipeline:
            # 1) normalization/neighbors -> 2) evidence gathering -> 3) synthesis -> 4) layman rewrite.
            _add("medication-normalization-agent")
            _add("medication-evidence-gathering-agent")
            _add("medication-answer-synthesis-agent")
            _add("layman-translator-agent")

        # Compatibility fallback if any dedicated stage agent is unavailable.
        if not chain:
            _add("medication-info-agent")
            _add("safety-contraindication-agent")
            _add("layman-translator-agent")

        if not chain:
            chain = [available_agents[0]]

        return chain

    def _has_medication_intent(self, grounded_context: dict[str, Any]) -> bool:
        if not isinstance(grounded_context, dict):
            return False
        metadata = grounded_context.get("metadata", {})
        if isinstance(metadata, dict):
            if str(metadata.get("medication_name") or "").strip():
                return True
            if metadata.get("force_medication") is True:
                return True
        return self._grounding_has_signal(grounded_context)

    async def _chat_with_chain(
        self,
        *,
        user: UserRecord,
        payload: AgentChatRequest,
        chain: list[str],
        on_tool_event: Callable[[dict[str, Any]], None] | None = None,
        grounded_context: dict[str, Any] | None = None,
        turn_index_offset: int = 0,
        record_agent_work: bool = True,
    ) -> AgentChatResponse:
        if not chain:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Agent chain cannot be empty")

        first_agent = self.get_agent_for_user(user=user, agent_id=chain[0])
        conversation = self._get_or_create_conversation(payload.conversation_id, participants=[first_agent.id, user.id, *chain])
        assistant_start_index = len([msg for msg in conversation.messages if msg.role == "assistant"])

        if grounded_context is None:
            grounded_context = await self._build_grounding_context(payload)

        resume_anchor_idx = self._resolve_resume_anchor(conversation=conversation, user_id=user.id, payload=payload)
        is_resuming_partial = resume_anchor_idx is not None
        if not is_resuming_partial:
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
        start_idx = 0
        current_input = payload.message
        if is_resuming_partial and resume_anchor_idx is not None:
            restored_turns = self._restore_completed_turns(
                user=user,
                conversation=conversation,
                chain=chain,
                grounded_context=grounded_context,
                anchor_idx=resume_anchor_idx,
                payload_message=payload.message,
            )
            if restored_turns:
                turns.extend(restored_turns)
                start_idx = len(restored_turns)
                current_input = restored_turns[-1].response

        conversation_tool_history = list(self._tool_history.get(conversation.conversation_id, []))

        for idx in range(start_idx, len(chain)):
            next_agent_id = chain[idx]
            current_agent = self.get_agent_for_user(user=user, agent_id=next_agent_id)
            stage_input = current_input
            if idx > 0:
                self._append_agent_handoff_message_if_missing(
                    conversation_id=conversation.conversation_id,
                    content=current_input,
                    sender=chain[idx - 1],
                )

            if on_tool_event:
                on_tool_event(
                    {
                        "event_type": "step_started",
                        "turn_index": idx + turn_index_offset,
                        "agent_id": current_agent.id,
                        "stage_input": stage_input,
                        "message": f"Starting {current_agent.name}",
                    }
                )

            mcp_tool_calls = await self._run_agent_mcp_tools(
                agent_id=current_agent.id,
                grounded_context=grounded_context,
                user_id=user.id,
                previous_turns=turns,
                on_tool_call=(
                    (
                        lambda call, idx=idx, aid=current_agent.id: on_tool_event(
                            {
                                "event_type": "tool_call",
                                "turn_index": idx + turn_index_offset,
                                "agent_id": aid,
                                "call": call,
                            }
                        )
                    )
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

            assistant_message = AgentMessage(
                role="assistant",
                content=response,
                sender=current_agent.id,
                timestamp=_utcnow(),
            )
            self._append_message(
                conversation.conversation_id,
                assistant_message,
            )
            self._remember_stage_tool_calls(
                conversation_id=conversation.conversation_id,
                message_timestamp=assistant_message.timestamp,
                mcp_tool_calls=mcp_tool_calls,
            )

            turns.append(
                AgentChatTurn(
                    agent_id=current_agent.id,
                    received_input=stage_input,
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

            if on_tool_event:
                on_tool_event(
                    {
                        "event_type": "step_completed",
                        "turn_index": idx + turn_index_offset,
                        "agent_id": current_agent.id,
                        "stage_output": response,
                        "next_stage_input": response,
                        "message": f"Completed {current_agent.name}",
                    }
                )

            current_input = response

        final_turn = turns[-1]
        response = AgentChatResponse(
            conversation_id=conversation.conversation_id,
            final_agent_id=final_turn.agent_id,
            final_response=final_turn.response,
            clinician_summary=final_turn.clinician_summary or final_turn.response,
            patient_summary=final_turn.patient_summary or final_turn.response,
            evidence_snippets=final_turn.evidence_snippets,
            source_links=final_turn.source_links,
            turns=turns,
        )
        if record_agent_work:
            self._record_agent_work(
                conversation_id=conversation.conversation_id,
                assistant_start_index=assistant_start_index,
                turns=turns,
            )
            response.agent_work_history = list(conversation.agent_work_history)
        return response

    def _resolve_resume_anchor(self, *, conversation: AgentConversation, user_id: str, payload: AgentChatRequest) -> int | None:
        metadata = payload.metadata if isinstance(payload.metadata, dict) else {}
        resume_requested = bool(metadata.get("resume_partial"))
        if not resume_requested:
            return None

        if not payload.conversation_id:
            return None

        target = payload.message.strip()
        if not target:
            return None

        for idx in range(len(conversation.messages) - 1, -1, -1):
            msg = conversation.messages[idx]
            if msg.role != "user":
                continue
            if str(msg.sender or "") != user_id:
                continue
            if msg.content.strip() != target:
                continue
            if any(item.role == "user" for item in conversation.messages[idx + 1 :]):
                return None
            return idx

        return None

    def _restore_completed_turns(
        self,
        *,
        user: UserRecord,
        conversation: AgentConversation,
        chain: list[str],
        grounded_context: dict[str, Any],
        anchor_idx: int,
        payload_message: str,
    ) -> list[AgentChatTurn]:
        turns: list[AgentChatTurn] = []
        expected_idx = 0
        tail = conversation.messages[anchor_idx + 1 :]

        for msg in tail:
            if msg.role != "assistant":
                continue
            if expected_idx >= len(chain):
                break

            expected_agent_id = chain[expected_idx]
            if str(msg.sender or "") != expected_agent_id:
                break

            agent = self.get_agent_for_user(user=user, agent_id=expected_agent_id)
            prior_response = turns[-1].response if turns else payload_message
            mcp_tool_calls = self._recall_stage_tool_calls(
                conversation_id=conversation.conversation_id,
                message_timestamp=msg.timestamp,
            )
            stage_context = {
                **grounded_context,
                "mcp_tool_calls": mcp_tool_calls,
                "mcp_tool_history": list(self._tool_history.get(conversation.conversation_id, []))[-20:],
            }
            thought_summary = self._build_thought_summary(
                agent_id=expected_agent_id,
                grounded_context=grounded_context,
                mcp_tool_calls=mcp_tool_calls,
            )
            clinician_summary, patient_summary = self._split_outputs(
                response=msg.content,
                agent_id=expected_agent_id,
                grounded_context=stage_context,
            )

            turns.append(
                AgentChatTurn(
                    agent_id=expected_agent_id,
                    received_input=prior_response,
                    response=msg.content,
                    provider=agent.provider,
                    model=agent.model,
                    thought_summary=thought_summary,
                    mcp_tool_calls=mcp_tool_calls,
                    clinician_summary=clinician_summary,
                    patient_summary=patient_summary,
                    evidence_snippets=stage_context["evidence_snippets"],
                    source_links=stage_context["source_links"],
                )
            )
            expected_idx += 1

        return turns

    def _remember_stage_tool_calls(
        self,
        *,
        conversation_id: str,
        message_timestamp: datetime,
        mcp_tool_calls: list[dict[str, Any]],
    ) -> None:
        cache_key = message_timestamp.isoformat()
        with self._lock:
            per_conversation = self._tool_calls_by_message.setdefault(conversation_id, {})
            per_conversation[cache_key] = [dict(item) for item in mcp_tool_calls if isinstance(item, dict)]

    def _recall_stage_tool_calls(self, *, conversation_id: str, message_timestamp: datetime) -> list[dict[str, Any]]:
        cache_key = message_timestamp.isoformat()
        per_conversation = self._tool_calls_by_message.get(conversation_id, {})
        cached = per_conversation.get(cache_key, [])
        return [dict(item) for item in cached if isinstance(item, dict)]

    def _append_agent_handoff_message_if_missing(self, *, conversation_id: str, content: str, sender: str) -> None:
        conversation = self._conversations.get(conversation_id)
        if conversation is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

        if conversation.messages:
            last = conversation.messages[-1]
            if last.role == "agent" and str(last.sender or "") == sender and last.content == content:
                return

        self._append_message(
            conversation_id,
            AgentMessage(
                role="agent",
                content=content,
                sender=sender,
                timestamp=_utcnow(),
            ),
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
            previous_turns=[],
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

    def delete_conversation(self, *, conversation_id: str, user_id: str) -> None:
        with self._lock:
            conversation = self._conversations.get(conversation_id)
            if conversation is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
            if user_id not in conversation.participants:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
            self._conversations.pop(conversation_id, None)
            self._tool_history.pop(conversation_id, None)
            self._tool_calls_by_message.pop(conversation_id, None)
            self._persist_conversations_locked()

    def delete_all_conversations_for_user(self, *, user_id: str) -> int:
        removed = 0
        with self._lock:
            conversation_ids = [
                cid
                for cid, conversation in self._conversations.items()
                if user_id in conversation.participants
            ]
            for cid in conversation_ids:
                self._conversations.pop(cid, None)
                self._tool_history.pop(cid, None)
                self._tool_calls_by_message.pop(cid, None)
                removed += 1
            self._persist_conversations_locked()
        return removed

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

    async def _invoke_agent_with_prompt(self, *, agent: AgentDefinition, prompt: str) -> str:
        provider_client = get_provider_client(agent.provider)
        messages = [
            {
                "role": "system",
                "content": agent.system_prompt,
            },
            {
                "role": "user",
                "content": prompt,
            },
        ]
        response = await provider_client.generate(agent, messages)
        if not self._is_empty_provider_response(response):
            return response
        return "{\"intent\": \"general\", \"confidence\": 0.3, \"rationale\": \"No response\"}"

    async def _invoke_agent_with_history_prompt(
        self,
        *,
        agent: AgentDefinition,
        conversation_id: str,
        prompt: str,
    ) -> str:
        provider_client = get_provider_client(agent.provider)
        messages = self._build_messages(
            agent=agent,
            conversation_id=conversation_id,
            grounded_context={"evidence_snippets": [], "source_links": [], "metadata": {}},
        )
        messages.append({"role": "user", "content": prompt})
        response = await provider_client.generate(agent, messages)
        if not self._is_empty_provider_response(response):
            return response
        return "{\"intent\": \"general\", \"confidence\": 0.3, \"rationale\": \"No response\"}"

    def _extract_intent_payload(self, response: str) -> tuple[dict[str, Any], str]:
        if not isinstance(response, str):
            return {}, ""
        lines = [line for line in response.splitlines() if line.strip()]
        if not lines:
            return {}, ""
        first = lines[0].strip()
        payload: dict[str, Any] = {}
        remaining = "\n".join(lines[1:]).strip()

        if first.lower().startswith("intent_json"):
            first = first.split(":", 1)[-1].strip()

        if first.startswith("{") and first.endswith("}"):
            try:
                parsed = json.loads(first)
            except Exception:
                parsed = None
            if isinstance(parsed, dict):
                payload = parsed
        if not payload:
            remaining = response.strip()
        return payload, remaining

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

        if not self._grounding_has_signal(grounded):
            return {
                "evidence_snippets": [],
                "source_links": [],
                "metadata": payload.metadata,
                "medication_guess": raw_name,
                "original_query": raw_name,
                "selected_query": raw_name,
                "query_candidates": candidates,
            }

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

    def _collect_pipeline_search_terms(
        self,
        *,
        grounded_context: dict[str, Any],
        previous_turns: list[AgentChatTurn],
    ) -> list[str]:
        seed_terms: list[str] = []

        for candidate in [
            grounded_context.get("selected_query"),
            grounded_context.get("canonical_name"),
            grounded_context.get("query"),
            grounded_context.get("original_query"),
        ]:
            token = str(candidate or "").strip()
            if token:
                seed_terms.append(token)

        query_candidates = grounded_context.get("query_candidates", [])
        if isinstance(query_candidates, list):
            for item in query_candidates:
                token = str(item).strip()
                if token:
                    seed_terms.append(token)

        for turn in previous_turns:
            if not isinstance(turn, AgentChatTurn):
                continue
            for call in turn.mcp_tool_calls:
                if not isinstance(call, dict):
                    continue
                tool_name = str(call.get("tool_name") or "").strip()
                if tool_name not in {"normalize_medication_name", "find_synonym_or_name_neighbors"}:
                    continue

                seed_terms.extend(self._extract_discovered_terms(call))

                output = call.get("output")
                if not isinstance(output, dict):
                    continue
                data = output.get("data")
                if not isinstance(data, dict):
                    continue

                neighbors = data.get("synonym_or_name_neighbors", [])
                if isinstance(neighbors, list):
                    for neighbor in neighbors:
                        if not isinstance(neighbor, dict):
                            continue
                        canonical = str(neighbor.get("canonical_name") or "").strip()
                        if canonical:
                            seed_terms.append(canonical)

                source_results = data.get("source_results", [])
                if isinstance(source_results, list):
                    for source_result in source_results:
                        if not isinstance(source_result, dict):
                            continue
                        items = source_result.get("items", [])
                        if not isinstance(items, list):
                            continue
                        for item in items:
                            if not isinstance(item, dict):
                                continue
                            canonical = str(item.get("canonical_name") or "").strip()
                            if canonical:
                                seed_terms.append(canonical)

        expanded: list[str] = []
        for term in seed_terms:
            for candidate in self._medication_query_candidates(term):
                normalized = str(candidate).strip()
                if normalized and normalized not in expanded:
                    expanded.append(normalized)

        return expanded

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
        if agent_id in {"medication-answer-synthesis-agent", "medication-evidence-gathering-agent"}:
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
        previous_turns: list[AgentChatTurn],
        on_tool_call: Callable[[dict[str, Any]], None] | None = None,
    ) -> list[dict[str, Any]]:
        metadata = grounded_context.get("metadata", {})
        medication_name = str(
            grounded_context.get("canonical_name")
            or grounded_context.get("query")
            or (metadata.get("medication_name") if isinstance(metadata, dict) else "")
            or ""
        ).strip()
        original_query = str(grounded_context.get("original_query") or "").strip()
        selected_query = str(grounded_context.get("selected_query") or "").strip()
        query_candidates = grounded_context.get("query_candidates", [])
        patient_context = metadata.get("patient_context", {}) if isinstance(metadata, dict) else {}
        current_medications = metadata.get("current_medications", []) if isinstance(metadata, dict) else []

        if not medication_name:
            return []

        calls: list[dict[str, Any]] = []

        async def _invoke(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
            stream_id = f"{agent_id}-{len(calls)}-{tool_name}"
            if on_tool_call:
                on_tool_call(
                    {
                        "stream_id": stream_id,
                        "tool_name": tool_name,
                        "status": "running",
                        "transport": "in-process",
                        "input": args,
                        "output": None,
                        "error": None,
                        "output_summary": "Pending...",
                    }
                )
                await asyncio.sleep(0)

            call = call_mcp_tool(tool_name, args=args, caller_id=user_id)
            call["stream_id"] = stream_id
            calls.append(call)
            if on_tool_call:
                on_tool_call(call)
                # Yield to event loop so stream clients receive tool events progressively.
                await asyncio.sleep(0)
            return call

        if agent_id == "medication-normalization-agent":
            seed_candidates = [selected_query, medication_name, original_query, *(query_candidates if isinstance(query_candidates, list) else [])]
            candidates: list[str] = []
            for candidate in seed_candidates:
                token = str(candidate).strip()
                if token and token not in candidates:
                    candidates.append(token)

            for attempt_name in candidates[:5]:
                await _invoke("normalize_medication_name", {"name": attempt_name})
                await _invoke("find_synonym_or_name_neighbors", {"name": attempt_name})
        elif agent_id in {"medication-evidence-gathering-agent", "medication-info-agent"}:
            search_terms = self._collect_pipeline_search_terms(
                grounded_context=grounded_context,
                previous_turns=previous_turns,
            )
            if not search_terms and medication_name:
                search_terms = self._medication_query_candidates(medication_name)

            attempted: set[str] = set()
            for term in search_terms[:6]:
                normalized = str(term).strip()
                if not normalized or normalized in attempted:
                    continue
                attempted.add(normalized)
                await _invoke("search_medication_facts", {"name": normalized})
                await _invoke("search_medication_indications", {"name": normalized})
                await _invoke("search_medication_contraindications", {"name": normalized})
        elif agent_id in {"medication-answer-synthesis-agent", "layman-translator-agent"}:
            # These stages should only consume prior stage outputs and not issue new MCP tool calls.
            pass
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
            self._persist_conversations_locked()
        return conversation

    def _append_message(self, conversation_id: str, message: AgentMessage) -> None:
        with self._lock:
            conversation = self._conversations.get(conversation_id)
            if conversation is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
            conversation.messages.append(message)
            self._persist_conversations_locked()

    def _record_agent_work(
        self,
        *,
        conversation_id: str,
        assistant_start_index: int,
        turns: list[AgentChatTurn],
    ) -> None:
        conversation = self._conversations.get(conversation_id)
        if conversation is None or not turns:
            return
        assistant_messages = [msg for msg in conversation.messages if msg.role == "assistant"]
        assistant_slice = assistant_messages[assistant_start_index:]
        entry = AgentWorkEntry(
            assistant_base_index=assistant_start_index,
            turns=turns,
            assistant_messages=assistant_slice,
        )
        conversation.agent_work_history.append(entry)
        self._persist_conversations_locked()

    def _persist_conversations_locked(self) -> None:
        if self._conversation_repository is None:
            return
        self._conversation_repository.save_conversations(list(self._conversations.values()))


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)
