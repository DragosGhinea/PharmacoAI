from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, status

from .agents_catalog import load_agent_definitions
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

    async def chat_with_agent(self, *, user: UserRecord, agent_id: str, payload: AgentChatRequest) -> AgentChatResponse:
        agent = self.get_agent_for_user(user=user, agent_id=agent_id)
        conversation = self._get_or_create_conversation(payload.conversation_id, participants=[agent.id, user.id])

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
        current_agent = agent
        current_input = payload.message

        chain = [agent_id] + [item for item in payload.handoff_to if item and item != agent_id]
        for idx, next_agent_id in enumerate(chain):
            if idx > 0:
                current_agent = self.get_agent_for_user(user=user, agent_id=next_agent_id)
                self._append_message(
                    conversation.conversation_id,
                    AgentMessage(
                        role="agent",
                        content=current_input,
                        sender=chain[idx - 1],
                        timestamp=_utcnow(),
                    ),
                )

            response = await self._invoke_agent(
                agent=current_agent,
                conversation_id=conversation.conversation_id,
                grounded_context=grounded_context,
            )

            clinician_summary, patient_summary = self._split_outputs(
                response=response,
                agent_id=current_agent.id,
                grounded_context=grounded_context,
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
                    clinician_summary=clinician_summary,
                    patient_summary=patient_summary,
                    evidence_snippets=grounded_context["evidence_snippets"],
                    source_links=grounded_context["source_links"],
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

        response = await self._invoke_agent(
            agent=to_agent,
            conversation_id=conversation.conversation_id,
            grounded_context=grounded_context,
        )
        clinician_summary, patient_summary = self._split_outputs(
            response=response,
            agent_id=to_agent.id,
            grounded_context=grounded_context,
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
                    clinician_summary=clinician_summary,
                    patient_summary=patient_summary,
                    evidence_snippets=grounded_context["evidence_snippets"],
                    source_links=grounded_context["source_links"],
                )
            ],
        )

    def get_conversation(self, conversation_id: str) -> AgentConversation:
        conversation = self._conversations.get(conversation_id)
        if conversation is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
        return conversation

    async def _invoke_agent(self, *, agent: AgentDefinition, conversation_id: str, grounded_context: dict[str, Any]) -> str:
        messages = self._build_messages(
            agent=agent,
            conversation_id=conversation_id,
            grounded_context=grounded_context,
        )
        provider_client = get_provider_client(agent.provider)
        return await provider_client.generate(agent, messages)

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

    async def _build_grounding_context(self, payload: AgentChatRequest) -> dict[str, Any]:
        raw_name = str(payload.metadata.get("medication_name", "")).strip()
        if not raw_name:
            raw_name = self._extract_medication_guess(payload.message)

        if not raw_name:
            return {"evidence_snippets": [], "source_links": []}

        return await get_grounded_medication_context(raw_name)

    def _extract_medication_guess(self, text: str) -> str:
        token = text.strip()
        if not token:
            return ""

        # Simple heuristic for MVP: first token group before punctuation.
        guess = token.split("?")[0].split(".")[0].split(",")[0]
        words = [part for part in guess.split() if part]
        if not words:
            return ""
        return " ".join(words[:3])

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
