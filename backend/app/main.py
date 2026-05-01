from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from time import perf_counter
from datetime import datetime, timezone
from uuid import uuid4

import stripe
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from fastapi import HTTPException, status
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from ..env_loader import load_root_env

load_root_env()

from .agents_schemas import (
    AgentChatRequest,
    AgentChatResponse,
    AgentConversation,
    AgentDefinition,
    AgentHandoffRequest,
    AgentListResponse,
    StreamCancelRequest,
)
from .agents_service import AgentsService
from .auth import get_current_user, require_admin, require_org_pharmacist
from .deps import get_agents_service, get_billing_service, get_user_service
from .schemas import (
    AuthLoginRequest,
    AuthLoginResponse,
    ChangePasswordRequest,
    ChangePasswordResponse,
    HealthResponse,
    MessageAddonCheckoutRequest,
    MessageAddonConfirmRequest,
    MessageAddonConfirmResponse,
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
from .billing import BillingService, MESSAGE_ADDON_PACKS
from .service import UserService
from .tiers import TIER_FEATURES, Tier

REQUEST_LOGGER = logging.getLogger("pharmacoai.backend.requests")
REQUEST_LOG_PATH = Path(
    os.getenv(
        "BACKEND_REQUEST_LOG_FILE",
        str(Path(__file__).resolve().parents[1] / "logs" / "requests.log"),
    )
)
REQUEST_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def _append_request_log_line(message: str) -> None:
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with REQUEST_LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(f"{timestamp} {message}\n")


if not REQUEST_LOGGER.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s [%(name)s] %(message)s",
        "%Y-%m-%dT%H:%M:%S",
    )
    handler.setFormatter(formatter)
    REQUEST_LOGGER.addHandler(handler)
REQUEST_LOGGER.setLevel(logging.INFO)
REQUEST_LOGGER.propagate = False

app = FastAPI(
    title="PharmacoAI Backend",
    version="0.1.0",
    description="JSON-backed user management with role and tier controls.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[],
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_http_requests(request: Request, call_next):
    started_at = perf_counter()
    method = request.method
    path = request.url.path
    if request.url.query:
        path = f"{path}?{request.url.query}"
    client = request.client.host if request.client else "-"

    try:
        response = await call_next(request)
    except Exception:
        duration_ms = (perf_counter() - started_at) * 1000
        failure_line = (
            f"request_failed method={method} path={path} client={client} duration_ms={duration_ms:.2f}"
        )
        REQUEST_LOGGER.exception(
            "request_failed method=%s path=%s client=%s duration_ms=%.2f",
            method,
            path,
            client,
            duration_ms,
        )
        _append_request_log_line(failure_line)
        raise

    duration_ms = (perf_counter() - started_at) * 1000
    request_line = (
        f"request method={method} path={path} status={response.status_code} "
        f"client={client} duration_ms={duration_ms:.2f}"
    )
    REQUEST_LOGGER.info(
        "request method=%s path=%s status=%s client=%s duration_ms=%.2f",
        method,
        path,
        response.status_code,
        client,
        duration_ms,
    )
    _append_request_log_line(request_line)
    return response


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
        owner_admin_id=user.owner_admin_id,
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


@app.get("/subscriptions/addons/packs")
def list_addon_packs() -> dict:
    return {
        pack_id: {"count": info["count"], "price_cents": info["price_cents"]}
        for pack_id, info in MESSAGE_ADDON_PACKS.items()
    }


@app.post("/subscriptions/addons/checkout", response_model=SubscriptionCheckoutResponse)
def create_addon_checkout(
    payload: MessageAddonCheckoutRequest,
    current_user: UserRecord = Depends(get_current_user),
    billing_service: BillingService = Depends(get_billing_service),
) -> SubscriptionCheckoutResponse:
    return billing_service.create_addon_checkout_session(payload.pack_id, current_user)


@app.post("/subscriptions/addons/confirm", response_model=MessageAddonConfirmResponse)
def confirm_addon_checkout(
    payload: MessageAddonConfirmRequest,
    billing_service: BillingService = Depends(get_billing_service),
) -> MessageAddonConfirmResponse:
    result = billing_service.finalize_addon_checkout(payload.session_id)
    return MessageAddonConfirmResponse(
        detail=f"{result['count']} messages added to your account",
        count=result["count"],
        pack_id=result["pack_id"],
    )


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
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    return service.simulate_message(user_id, payload.prompt)


@app.get("/agents", response_model=AgentListResponse)
def list_agents(
    current_user: UserRecord = Depends(require_org_pharmacist),
    service: AgentsService = Depends(get_agents_service),
) -> AgentListResponse:
    return AgentListResponse(agents=service.list_agents_for_user(user=current_user))


@app.get("/agents/{agent_id}", response_model=AgentDefinition)
def get_agent(
    agent_id: str,
    current_user: UserRecord = Depends(require_org_pharmacist),
    service: AgentsService = Depends(get_agents_service),
) -> AgentDefinition:
    return service.get_agent_for_user(user=current_user, agent_id=agent_id)


@app.post("/agents/{agent_id}/chat", response_model=AgentChatResponse)
async def chat_with_agent(
    agent_id: str,
    payload: AgentChatRequest,
    current_user: UserRecord = Depends(require_org_pharmacist),
    service: AgentsService = Depends(get_agents_service),
) -> AgentChatResponse:
    return await service.chat_with_agent(user=current_user, agent_id=agent_id, payload=payload)


@app.post("/agents/chat", response_model=AgentChatResponse)
async def chat_with_orchestrator(
    payload: AgentChatRequest,
    current_user: UserRecord = Depends(require_org_pharmacist),
    service: AgentsService = Depends(get_agents_service),
    user_service: UserService = Depends(get_user_service),
) -> AgentChatResponse:
    sim_result = user_service.simulate_message(current_user.id, payload.message)
    if not sim_result.accepted:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=sim_result.reason)
    return await service.chat_with_orchestrator(user=current_user, payload=payload)


@app.post("/agents/chat/stream")
async def chat_with_orchestrator_stream(
    payload: AgentChatRequest,
    current_user: UserRecord = Depends(require_org_pharmacist),
    service: AgentsService = Depends(get_agents_service),
    user_service: UserService = Depends(get_user_service),
) -> StreamingResponse:
    sim_result = user_service.simulate_message(current_user.id, payload.message)
    if not sim_result.accepted:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=sim_result.reason)

    queue: asyncio.Queue[dict[str, object]] = asyncio.Queue()
    request_id = str(uuid4())

    def on_tool_event(event: dict[str, object]) -> None:
        event_type = str(event.get("event_type") or "tool_call")
        queue.put_nowait({"type": event_type, **event})

    async def run_chat() -> None:
        try:
            result = await service.chat_with_orchestrator(
                user=current_user,
                payload=payload,
                on_tool_event=on_tool_event,
            )
            await queue.put({"type": "final", "data": result.model_dump(mode="json")})
        except asyncio.CancelledError:
            return
        except HTTPException as exc:
            detail = exc.detail
            if isinstance(detail, str) and detail.strip():
                message = detail.strip()
            else:
                message = f"HTTP {exc.status_code}"
            await queue.put({"type": "error", "message": message, "status_code": exc.status_code})
        except Exception as exc:  # pragma: no cover - runtime fallback
            message = str(exc).strip() or f"{exc.__class__.__name__} during orchestrator stream"
            await queue.put({"type": "error", "message": message})
        finally:
            service.clear_stream_task(request_id=request_id)
            await queue.put({"type": "done"})

    task = asyncio.create_task(run_chat())
    service.register_stream_task(request_id=request_id, user_id=current_user.id, task=task)
    queue.put_nowait({"type": "started", "request_id": request_id})

    async def event_stream() -> object:
        try:
            while True:
                item = await queue.get()
                yield "data: " + json.dumps(item, ensure_ascii=True) + "\n\n"
                # Hand control back to the loop so chunks are flushed progressively.
                await asyncio.sleep(0)
                if item.get("type") == "done":
                    break
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/agents/chat/stream/cancel")
def cancel_chat_stream(
    payload: StreamCancelRequest,
    current_user: UserRecord = Depends(get_current_user),
    service: AgentsService = Depends(get_agents_service),
) -> dict[str, str]:
    cancelled = service.cancel_stream_task(request_id=payload.request_id, user_id=current_user.id)
    if not cancelled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stream not found")
    return {"status": "cancelled"}


@app.post("/agents/handoff", response_model=AgentChatResponse)
async def handoff_between_agents(
    payload: AgentHandoffRequest,
    current_user: UserRecord = Depends(require_org_pharmacist),
    service: AgentsService = Depends(get_agents_service),
) -> AgentChatResponse:
    return await service.handoff(user=current_user, payload=payload)


@app.get("/agents/conversations/{conversation_id}", response_model=AgentConversation)
def get_conversation(
    conversation_id: str,
    _current_user: UserRecord = Depends(get_current_user),
    service: AgentsService = Depends(get_agents_service),
) -> AgentConversation:
    return service.get_conversation(conversation_id)


@app.delete("/agents/conversations/{conversation_id}")
def delete_conversation(
    conversation_id: str,
    current_user: UserRecord = Depends(get_current_user),
    service: AgentsService = Depends(get_agents_service),
) -> dict[str, str]:
    service.delete_conversation(conversation_id=conversation_id, user_id=current_user.id)
    return {"detail": "Conversation deleted"}


@app.delete("/agents/conversations")
def delete_all_conversations(
    current_user: UserRecord = Depends(get_current_user),
    service: AgentsService = Depends(get_agents_service),
) -> dict[str, int]:
    removed = service.delete_all_conversations_for_user(user_id=current_user.id)
    return {"removed": removed}
