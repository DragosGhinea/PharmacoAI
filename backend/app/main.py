from __future__ import annotations

import json
import os

import stripe
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from .auth import get_current_user, require_admin
from .deps import get_billing_service, get_user_service
from .schemas import (
    AuthLoginRequest,
    AuthLoginResponse,
    ChangePasswordRequest,
    ChangePasswordResponse,
    HealthResponse,
    MessageSimulationRequest,
    MessageSimulationResponse,
    SubscriptionConfirmRequest,
    SubscriptionConfirmResponse,
    SubscriptionCheckoutRequest,
    SubscriptionCheckoutResponse,
    TierInfo,
    UserCreate,
    UserRecord,
    UserResponse,
    UserUpdate,
    to_user_response,
    utcnow,
)
from .billing import BillingService
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
        "http://localhost:5174",
        "http://127.0.0.1:5174",
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
            admin_user_limit=features["admin_user_limit"],
            supports_message_addons=features["supports_message_addons"],
            monthly_price_cents=features["monthly_price_cents"],
        )
        for tier, features in TIER_FEATURES.items()
    ]


@app.post("/subscriptions/checkout", response_model=SubscriptionCheckoutResponse)
def create_subscription_checkout(
    payload: SubscriptionCheckoutRequest,
    current_user: UserRecord = Depends(get_current_user),
    billing_service: BillingService = Depends(get_billing_service),
) -> SubscriptionCheckoutResponse:
    return billing_service.create_checkout_session(payload, current_user)


@app.post("/subscriptions/confirm", response_model=SubscriptionConfirmResponse)
def confirm_subscription(
    payload: SubscriptionConfirmRequest,
    billing_service: BillingService = Depends(get_billing_service),
) -> SubscriptionConfirmResponse:
    billing_service.finalize_checkout_session(payload.session_id)
    return SubscriptionConfirmResponse(detail="Subscription activated")


@app.post("/subscriptions/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: str | None = Header(default=None, alias="Stripe-Signature"),
    billing_service: BillingService = Depends(get_billing_service),
) -> dict[str, str]:
    payload = await request.body()
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")

    if webhook_secret:
        try:
            event = stripe.Webhook.construct_event(payload, stripe_signature, webhook_secret)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Invalid webhook signature: {exc}")
    else:
        try:
            event = json.loads(payload.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid webhook payload: {exc}")

    if event.get("type") == "checkout.session.completed":
        session = event.get("data", {}).get("object", {})
        session_id = session.get("id")
        if session_id:
            billing_service.finalize_checkout_session(session_id)

    return {"status": "ok"}


@app.get("/users", response_model=list[UserResponse])
def list_users(
    current_admin: UserRecord = Depends(require_admin),
    service: UserService = Depends(get_user_service),
) -> list[UserResponse]:
    return [to_user_response(user) for user in service.list_users_for_admin(current_admin.id)]


@app.get("/users/me", response_model=UserResponse)
def get_me(
    current_user: UserRecord = Depends(get_current_user),
    billing_service: BillingService = Depends(get_billing_service),
) -> UserResponse:
    user_response = to_user_response(current_user)
    active_subscription = billing_service.get_active_subscription(current_user.id)
    if active_subscription and active_subscription.get("tier"):
        tier_value = active_subscription["tier"]
        tier = Tier(tier_value)
        tier_features = TIER_FEATURES[tier]
        user_response = user_response.model_copy(
            update={
                "tier": tier,
                "monthly_message_limit": tier_features["monthly_message_limit"],
                "allowed_agents": tier_features["allowed_agents"],
            }
        )
    return user_response


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


@app.post("/users", response_model=UserResponse)
def create_user(
    payload: UserCreate,
    current_admin: UserRecord = Depends(require_admin),
    service: UserService = Depends(get_user_service),
) -> UserResponse:
    user = service.create_user_for_admin(current_admin, payload)
    return to_user_response(user)


@app.put("/users/{user_id}", response_model=UserResponse)
def update_user(
    user_id: str,
    payload: UserUpdate,
    current_admin: UserRecord = Depends(require_admin),
    service: UserService = Depends(get_user_service),
) -> UserResponse:
    user = service.update_user_for_admin(current_admin, user_id, payload)
    return to_user_response(user)


@app.delete("/users/{user_id}")
def delete_user(
    user_id: str,
    current_admin: UserRecord = Depends(require_admin),
    service: UserService = Depends(get_user_service),
) -> dict[str, str]:
    service.delete_user_for_admin(current_admin, user_id)
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
