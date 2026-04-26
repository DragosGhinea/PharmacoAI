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
        current_admin: UserRecord,
    ) -> SubscriptionCheckoutResponse:
        tier_features = TIER_FEATURES[payload.tier]
        is_paid_plan = tier_features["monthly_price_cents"] > 0

        stripe_secret_key = os.getenv("STRIPE_SECRET_KEY", DEFAULT_STRIPE_TEST_KEY)

        subscription_id = f"sub-{uuid4().hex[:12]}"
        subscription_record = {
            "id": subscription_id,
            "user_id": current_admin.id,
            "tier": payload.tier,
            "pharmacy_name": None,
            "contact_name": current_admin.full_name,
            "email": current_admin.email,
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
            self._append_record(subscription_record)
            frontend_base_url = os.getenv("FRONTEND_BASE_URL", "http://localhost:5174")
            return SubscriptionCheckoutResponse(
                subscription_id=subscription_id,
                checkout_session_id="free-plan",
                checkout_url=f"{frontend_base_url}/subscribe/success?subscription_id={subscription_id}",
            )

        stripe.api_key = stripe_secret_key
        frontend_base_url = os.getenv("FRONTEND_BASE_URL", "http://localhost:5174")

        product_name = f"PharmacoAI {payload.tier.value.capitalize()} Plan"
        try:
            checkout_session = stripe.checkout.Session.create(
                mode="payment",
                customer_email=current_admin.email,
                metadata={
                    "subscription_id": subscription_id,
                    "tier": payload.tier.value,
                    "email": current_admin.email,
                    "admin_user_id": current_admin.id,
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
                            "unit_amount": tier_features["monthly_price_cents"],
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
        self._append_record(subscription_record)

        return SubscriptionCheckoutResponse(
            subscription_id=subscription_id,
            checkout_session_id=checkout_session.id,
            checkout_url=checkout_session.url,
        )

    def _append_record(self, record: dict) -> None:
        payload = self._read_payload()
        payload.setdefault("subscriptions", []).append(record)
        with self._lock:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            with self.file_path.open("w", encoding="utf-8") as file_pointer:
                json.dump(payload, file_pointer, indent=2)

    def _read_payload(self) -> dict:
        if not self.file_path.exists():
            return {"subscriptions": []}

        with self.file_path.open("r", encoding="utf-8") as file_pointer:
            content = file_pointer.read().strip()
            if not content:
                return {"subscriptions": []}
            return json.loads(content)
