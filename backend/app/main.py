from __future__ import annotations

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .auth import get_current_user, require_admin
from .deps import get_user_service
from .schemas import (
    AuthLoginRequest,
    AuthLoginResponse,
    ChangePasswordRequest,
    ChangePasswordResponse,
    HealthResponse,
    MessageSimulationRequest,
    MessageSimulationResponse,
    TierInfo,
    UserCreate,
    UserRecord,
    UserResponse,
    UserUpdate,
    to_user_response,
    utcnow,
)
from .service import UserService
from .tiers import TIER_FEATURES, Tier

app = FastAPI(
    title="PharmacoAI Backend",
    version="0.1.0",
    description="JSON-backed user management with role and tier controls.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    return HealthResponse(status="ok", timestamp=utcnow())


@app.post("/auth/login", response_model=AuthLoginResponse)
def auth_login(payload: AuthLoginRequest, service: UserService = Depends(get_user_service)) -> AuthLoginResponse:
    user = service.authenticate_user(payload.email, payload.password)
    return AuthLoginResponse(
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        tier=user.tier,
        is_active=user.is_active,
    )


@app.get("/tiers", response_model=list[TierInfo])
def list_tiers() -> list[TierInfo]:
    return [
        TierInfo(
            tier=tier,
            monthly_message_limit=features["monthly_message_limit"],
            allowed_agents=features["allowed_agents"],
        )
        for tier, features in TIER_FEATURES.items()
    ]


@app.get("/users", response_model=list[UserResponse], dependencies=[Depends(require_admin)])
def list_users(service: UserService = Depends(get_user_service)) -> list[UserResponse]:
    return [to_user_response(user) for user in service.list_users()]


@app.get("/users/me", response_model=UserResponse)
def get_me(current_user: UserRecord = Depends(get_current_user)) -> UserResponse:
    return to_user_response(current_user)


@app.post("/users/me/password", response_model=ChangePasswordResponse)
def change_my_password(
    payload: ChangePasswordRequest,
    current_user: UserRecord = Depends(get_current_user),
    service: UserService = Depends(get_user_service),
) -> ChangePasswordResponse:
    service.change_password(current_user.id, payload.current_password, payload.new_password)
    return ChangePasswordResponse(detail="Password updated successfully")


@app.get("/users/{user_id}", response_model=UserResponse)
def get_user(
    user_id: str,
    current_user: UserRecord = Depends(get_current_user),
    service: UserService = Depends(get_user_service),
) -> UserResponse:
    if current_user.role != "admin" and current_user.id != user_id:
        from fastapi import HTTPException, status

        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    return to_user_response(service.get_user(user_id))


@app.post("/users", response_model=UserResponse, dependencies=[Depends(require_admin)])
def create_user(payload: UserCreate, service: UserService = Depends(get_user_service)) -> UserResponse:
    user = service.create_user(payload)
    return to_user_response(user)


@app.put("/users/{user_id}", response_model=UserResponse, dependencies=[Depends(require_admin)])
def update_user(user_id: str, payload: UserUpdate, service: UserService = Depends(get_user_service)) -> UserResponse:
    user = service.update_user(user_id, payload)
    return to_user_response(user)


@app.delete("/users/{user_id}", dependencies=[Depends(require_admin)])
def delete_user(user_id: str, service: UserService = Depends(get_user_service)) -> dict[str, str]:
    service.delete_user(user_id)
    return {"detail": "User deleted"}


@app.post("/users/{user_id}/messages", response_model=MessageSimulationResponse)
def simulate_message(
    user_id: str,
    payload: MessageSimulationRequest,
    current_user: UserRecord = Depends(get_current_user),
    service: UserService = Depends(get_user_service),
) -> MessageSimulationResponse:
    if current_user.role != "admin" and current_user.id != user_id:
        from fastapi import HTTPException, status

        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    return service.simulate_message(user_id, payload.prompt)
