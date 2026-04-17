from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .tiers import TIER_FEATURES, Tier


class Role(str, Enum):
    ADMIN = "admin"
    PHARMACIST = "pharmacist"


class UserBase(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    full_name: str = Field(min_length=2, max_length=120)
    tier: Tier
    role: Role = Role.PHARMACIST
    is_active: bool = True


class UserCreate(UserBase):
    password: str = Field(min_length=6, max_length=128)


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str | None = Field(default=None, min_length=5, max_length=254)
    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    tier: Tier | None = None
    role: Role | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=6, max_length=128)


class UserRecord(UserBase):
    id: str
    password: str = ""
    monthly_messages_used: int = 0
    created_at: datetime
    updated_at: datetime


class UserResponse(BaseModel):
    id: str
    email: str
    full_name: str
    role: Role
    tier: Tier
    is_active: bool
    monthly_messages_used: int
    monthly_message_limit: int
    allowed_agents: list[str]
    created_at: datetime
    updated_at: datetime


class TierInfo(BaseModel):
    tier: Tier
    monthly_message_limit: int
    allowed_agents: list[str]


class MessageSimulationRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=3000)


class MessageSimulationResponse(BaseModel):
    user_id: str
    tier: Tier
    accepted: bool
    reason: str
    usage: dict[str, int]
    placeholder_agent_reply: str


class ErrorMessage(BaseModel):
    detail: str


class HealthResponse(BaseModel):
    status: Literal["ok"]
    timestamp: datetime


class AuthLoginRequest(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=1, max_length=128)


class AuthLoginResponse(BaseModel):
    user_id: str
    email: str
    full_name: str
    role: Role
    tier: Tier
    is_active: bool


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=6, max_length=128)


class ChangePasswordResponse(BaseModel):
    detail: str


def to_user_response(user: UserRecord) -> UserResponse:
    tier_features = TIER_FEATURES[user.tier]
    return UserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        tier=user.tier,
        is_active=user.is_active,
        monthly_messages_used=user.monthly_messages_used,
        monthly_message_limit=tier_features["monthly_message_limit"],
        allowed_agents=tier_features["allowed_agents"],
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
