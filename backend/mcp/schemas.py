from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class MCPWarning(BaseModel):
    severity: str
    code: str
    capability: str
    message: str
    missing_fields: list[str] = Field(default_factory=list)
    recommended_next_action: str | None = None


class MCPError(BaseModel):
    code: str
    message: str
    retry_after_seconds: int | None = None


class EvidenceReference(BaseModel):
    uri: str
    snippets: list[str] = Field(default_factory=list)


class ToolEnvelope(BaseModel):
    ok: bool
    risk_tier: str
    warnings: list[MCPWarning] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)
    error: MCPError | None = None
