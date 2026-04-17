from __future__ import annotations

from uuid import uuid4

from fastapi import HTTPException, status

from .repository import UserRepository
from .schemas import MessageSimulationResponse, UserCreate, UserRecord, UserUpdate, utcnow
from .tiers import TIER_FEATURES

DEFAULT_ADMIN_PASSWORD = "pharmacoai123"


class UserService:
    def __init__(self, repository: UserRepository) -> None:
        self.repository = repository

    def list_users(self) -> list[UserRecord]:
        return self.repository.list_users()

    def get_user(self, user_id: str) -> UserRecord:
        user = self._find_by_id(user_id)
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        return user

    def create_user(self, payload: UserCreate) -> UserRecord:
        users = self.repository.list_users()
        if any(existing.email.lower() == payload.email.lower() for existing in users):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A user with this email already exists",
            )

        now = utcnow()
        user = UserRecord(
            id=f"usr-{uuid4().hex[:10]}",
            email=payload.email,
            full_name=payload.full_name,
            role=payload.role,
            tier=payload.tier,
            is_active=payload.is_active,
            password=payload.password,
            monthly_messages_used=0,
            created_at=now,
            updated_at=now,
        )
        users.append(user)
        self.repository.save_users(users)
        return user

    def update_user(self, user_id: str, payload: UserUpdate) -> UserRecord:
        users = self.repository.list_users()
        idx = next((i for i, user in enumerate(users) if user.id == user_id), None)
        if idx is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        current = users[idx]
        updates = payload.model_dump(exclude_none=True)

        if "email" in updates:
            email_value = str(updates["email"])
            for other in users:
                if other.id != current.id and other.email.lower() == email_value.lower():
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="A user with this email already exists",
                    )

        merged = current.model_copy(update={**updates, "updated_at": utcnow()})
        users[idx] = merged
        self.repository.save_users(users)
        return merged

    def delete_user(self, user_id: str) -> None:
        users = self.repository.list_users()
        filtered = [user for user in users if user.id != user_id]
        if len(filtered) == len(users):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        self.repository.save_users(filtered)

    def simulate_message(self, user_id: str, prompt: str) -> MessageSimulationResponse:
        users = self.repository.list_users()
        idx = next((i for i, user in enumerate(users) if user.id == user_id), None)
        if idx is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        user = users[idx]
        if not user.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is inactive")

        tier_features = TIER_FEATURES[user.tier]
        message_limit = tier_features["monthly_message_limit"]

        if user.monthly_messages_used >= message_limit:
            return MessageSimulationResponse(
                user_id=user.id,
                tier=user.tier,
                accepted=False,
                reason="Monthly message limit reached for this tier",
                usage={
                    "used": user.monthly_messages_used,
                    "limit": message_limit,
                    "remaining": 0,
                },
                placeholder_agent_reply="Message blocked. Upgrade plan for more AI interactions.",
            )

        user.monthly_messages_used += 1
        user.updated_at = utcnow()
        users[idx] = user
        self.repository.save_users(users)

        return MessageSimulationResponse(
            user_id=user.id,
            tier=user.tier,
            accepted=True,
            reason="Message accepted by placeholder AI pipeline",
            usage={
                "used": user.monthly_messages_used,
                "limit": message_limit,
                "remaining": message_limit - user.monthly_messages_used,
            },
            placeholder_agent_reply=(
                "[placeholder-agent] AI response generation will be wired in the next milestone. "
                f"Prompt length received: {len(prompt)} characters."
            ),
        )

    def authenticate_user(self, email: str, password: str) -> UserRecord:
        users = self.repository.list_users()
        user = next((item for item in users if item.email.lower() == email.lower()), None)

        if user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

        if not user.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is inactive")

        expected_password = user.password
        if not expected_password and user.role == "admin" and user.id == "admin-0001":
            expected_password = DEFAULT_ADMIN_PASSWORD

        if not expected_password:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Password is not set for this account. Ask an admin to reset it.",
            )

        if expected_password != password:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

        return user

    def change_password(self, user_id: str, current_password: str, new_password: str) -> None:
        users = self.repository.list_users()
        idx = next((i for i, user in enumerate(users) if user.id == user_id), None)
        if idx is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        user = users[idx]
        expected_password = user.password
        if not expected_password and user.role == "admin" and user.id == "admin-0001":
            expected_password = DEFAULT_ADMIN_PASSWORD

        if expected_password != current_password:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Current password is incorrect")

        if current_password == new_password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="New password must be different from current password",
            )

        user.password = new_password
        user.updated_at = utcnow()
        users[idx] = user
        self.repository.save_users(users)

    def _find_by_id(self, user_id: str) -> UserRecord | None:
        users = self.repository.list_users()
        return next((user for user in users if user.id == user_id), None)
