from __future__ import annotations

from fastapi import Depends, Header, HTTPException, status

from .deps import get_user_service
from .schemas import Role, UserRecord
from .service import UserService


async def get_current_user(
    service: UserService = Depends(get_user_service),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> UserRecord:
    if not x_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-User-Id header",
        )

    user = service.get_user(x_user_id)
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user",
        )
    return user


async def require_admin(current_user: UserRecord = Depends(get_current_user)) -> UserRecord:
    if current_user.role != Role.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    return current_user
