from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class AgentProvider(str, Enum):
    API = "api"
    GEMINI = "gemini"


class AgentDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=3, max_length=80)
    name: str = Field(min_length=3, max_length=120)
    description: str = Field(min_length=8, max_length=1000)
    provider: AgentProvider
    model: str = Field(min_length=2, max_length=120)
    system_prompt: str = Field(min_length=8, max_length=4000)
    api_key_env: str = Field(min_length=3, max_length=120)
    base_url: str | None = Field(default=None, max_length=500)
    style_tags: list[str] = Field(default_factory=list)
    risk_tier: Literal["informational", "clinical-risk"] = "informational"
    temperature: float = Field(default=0.2, ge=0.0, le=1.0)
    enabled: bool = True


class AgentMessage(BaseModel):
    role: Literal["system", "user", "assistant", "agent"]
    content: str = Field(min_length=1, max_length=12000)
    sender: str | None = Field(default=None, max_length=80)
    timestamp: datetime


class AgentChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    conversation_id: str | None = Field(default=None, max_length=120)
    handoff_to: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentChatTurn(BaseModel):
    agent_id: str
    received_input: str | None = None
    response: str
    provider: AgentProvider
    model: str
    thought_summary: str | None = None
    mcp_tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    clinician_summary: str | None = None
    patient_summary: str | None = None
    evidence_snippets: list[str] = Field(default_factory=list)
    source_links: list[str] = Field(default_factory=list)


class AgentChatResponse(BaseModel):
    conversation_id: str
    final_agent_id: str
    final_response: str
    clinician_summary: str
    patient_summary: str
    evidence_snippets: list[str] = Field(default_factory=list)
    source_links: list[str] = Field(default_factory=list)
    turns: list[AgentChatTurn] = Field(default_factory=list)


class AgentHandoffRequest(BaseModel):
    from_agent_id: str = Field(min_length=3, max_length=80)
    to_agent_id: str = Field(min_length=3, max_length=80)
    message: str = Field(min_length=1, max_length=8000)
    conversation_id: str | None = Field(default=None, max_length=120)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentConversation(BaseModel):
    conversation_id: str
    participants: list[str]
    messages: list[AgentMessage]


class AgentListResponse(BaseModel):
    agents: list[AgentDefinition]
