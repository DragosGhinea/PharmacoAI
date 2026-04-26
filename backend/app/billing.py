from __future__ import annotations

import json
import os
from pathlib import Path
from threading import Lock
from uuid import uuid4

import stripe
from fastapi import HTTPException, status

from .schemas import SubscriptionCheckoutRequest, SubscriptionCheckoutResponse, UserRecord
from .service import UserService
from .tiers import TIER_FEATURES, Tier

DEFAULT_STRIPE_TEST_KEY = "sk_test_51TOwyYQrjQhNHuTmR91B1znC0zV4Apidm0lEiie1sGUVCdUJfNBZuuVnaSdtiIpy7tMKbvBbGlM4TupbPIbchpyX00lwWW1B12"


class BillingService:
    def __init__(self, file_path: Path, user_service: UserService) -> None:
        self.file_path = file_path
        self.user_service = user_service
        self._lock = Lock()

    def create_checkout_session(
        self,
        payload: SubscriptionCheckoutRequest,
        current_user: UserRecord,
    ) -> SubscriptionCheckoutResponse:
        tier_features = TIER_FEATURES[payload.tier]
        target_price_cents = int(tier_features["monthly_price_cents"])
        active_subscription = self.get_active_subscription(current_user.id)
        effective_price_cents = target_price_cents

        if active_subscription and active_subscription.get("tier"):
            current_tier = Tier(active_subscription["tier"])
            current_price_cents = int(TIER_FEATURES[current_tier]["monthly_price_cents"])
            if target_price_cents > current_price_cents:
                effective_price_cents = target_price_cents - current_price_cents

        is_paid_plan = effective_price_cents > 0

        stripe_secret_key = os.getenv("STRIPE_SECRET_KEY", DEFAULT_STRIPE_TEST_KEY)

        subscription_id = f"sub-{uuid4().hex[:12]}"
        subscription_record = {
            "id": subscription_id,
            "user_id": current_user.id,
            "tier": payload.tier,
            "previous_tier": active_subscription.get("tier") if active_subscription else None,
            "price_cents": effective_price_cents,
            "pharmacy_name": None,
            "contact_name": current_user.full_name,
            "email": current_user.email,
            "phone": None,
            "address_line1": None,
            "city": None,
            "country": None,
            "admin_user_limit": tier_features["admin_user_limit"],
            "supports_message_addons": tier_features["supports_message_addons"],
            "status": "pending_payment",
            "checkout_session_id": None,
        }

        # Free plan does not require payment. We keep one flow and still create a subscription record.
        if not is_paid_plan:
            subscription_record["status"] = "active"
            self.user_service.ensure_org_admin(current_user.id, payload.tier)
            self._append_and_activate(subscription_record)
            frontend_base_url = os.getenv("FRONTEND_BASE_URL", "http://localhost:5173")
            return SubscriptionCheckoutResponse(
                subscription_id=subscription_id,
                checkout_session_id="free-plan",
                checkout_url=f"{frontend_base_url}/subscribe/success?subscription_id={subscription_id}",
            )

        stripe.api_key = stripe_secret_key
        frontend_base_url = os.getenv("FRONTEND_BASE_URL", "http://localhost:5173")

        product_name = f"PharmacoAI {payload.tier.value.capitalize()} Plan"
        try:
            checkout_session = stripe.checkout.Session.create(
                mode="payment",
                customer_email=current_user.email,
                metadata={
                    "subscription_id": subscription_id,
                    "tier": payload.tier.value,
                    "email": current_user.email,
                    "admin_user_id": current_user.id,
                },
                line_items=[
                    {
                        "price_data": {
                            "currency": "usd",
                            "product_data": {
                                "name": product_name,
                                "description": (
                                    "Includes team seats, agent access, and monthly message allowance. "
                                    "Custom message add-ons are available for all plans."
                                ),
                            },
                            "unit_amount": effective_price_cents,
                        },
                        "quantity": 1,
                    }
                ],
                success_url=f"{frontend_base_url}/subscribe/success?session_id={{CHECKOUT_SESSION_ID}}",
                cancel_url=f"{frontend_base_url}/?checkout=cancel&subscription_id={subscription_id}",
            )
        except Exception as stripe_error:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Could not initialize Stripe checkout: {stripe_error}",
            )

        subscription_record["checkout_session_id"] = checkout_session.id
        payload = self._read_payload()
        payload.setdefault("subscriptions", []).append(subscription_record)
        with self._lock:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            with self.file_path.open("w", encoding="utf-8") as file_pointer:
                json.dump(payload, file_pointer, indent=2)

        return SubscriptionCheckoutResponse(
            subscription_id=subscription_id,
            checkout_session_id=checkout_session.id,
            checkout_url=checkout_session.url,
        )

    def finalize_checkout_session(self, session_id: str) -> None:
        payload = self._read_payload()
        subscriptions = payload.get("subscriptions", [])
        updated = False

        for record in subscriptions:
            if record.get("checkout_session_id") != session_id:
                continue
            if record.get("status") == "active":
                return

            record["status"] = "active"
            self._deactivate_other_subscriptions(subscriptions, record)
            user_id = str(record.get("user_id"))
            tier_value = record.get("tier")
            if tier_value:
                self.user_service.ensure_org_admin(user_id, Tier(tier_value))
            updated = True
            break

        if not updated:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscription not found")

        with self._lock:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            with self.file_path.open("w", encoding="utf-8") as file_pointer:
                json.dump(payload, file_pointer, indent=2)

    def get_active_subscription(self, user_id: str) -> dict | None:
        payload = self._read_payload()
        subscriptions = payload.get("subscriptions", [])
        active = [sub for sub in subscriptions if sub.get("user_id") == user_id and sub.get("status") == "active"]
        if not active:
            return None
        return active[-1]

    def _append_and_activate(self, record: dict) -> None:
        payload = self._read_payload()
        subscriptions = payload.setdefault("subscriptions", [])
        subscriptions.append(record)
        self._deactivate_other_subscriptions(subscriptions, record)
        with self._lock:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            with self.file_path.open("w", encoding="utf-8") as file_pointer:
                json.dump(payload, file_pointer, indent=2)

    def _deactivate_other_subscriptions(self, subscriptions: list[dict], active_record: dict) -> None:
        active_user_id = active_record.get("user_id")
        active_id = active_record.get("id")
        for record in subscriptions:
            if record.get("user_id") != active_user_id:
                continue
            if record.get("id") == active_id:
                continue
            if record.get("status") == "active":
                record["status"] = "inactive"

    def _read_payload(self) -> dict:
        if not self.file_path.exists():
            return {"subscriptions": []}

        with self.file_path.open("r", encoding="utf-8") as file_pointer:
            content = file_pointer.read().strip()
            if not content:
                return {"subscriptions": []}
            return json.loads(content)
