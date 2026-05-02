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

MESSAGE_ADDON_PACKS: dict[str, dict] = {
    "5":  {"count": 5,  "price_cents": 99},
    "10": {"count": 10, "price_cents": 199},
    "50": {"count": 50, "price_cents": 899},
}


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

    def create_addon_checkout_session(
        self,
        pack_id: str,
        current_user: UserRecord,
    ) -> SubscriptionCheckoutResponse:
        pack = MESSAGE_ADDON_PACKS.get(pack_id)
        if pack is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown addon pack: {pack_id}")

        count = int(pack["count"])
        price_cents = int(pack["price_cents"])
        addon_id = f"addon-{uuid4().hex[:12]}"

        addon_record: dict = {
            "id": addon_id,
            "user_id": current_user.id,
            "pack_id": pack_id,
            "count": count,
            "price_cents": price_cents,
            "status": "pending_payment",
            "checkout_session_id": None,
        }

        stripe_secret_key = os.getenv("STRIPE_SECRET_KEY", DEFAULT_STRIPE_TEST_KEY)
        frontend_base_url = os.getenv("FRONTEND_BASE_URL", "http://localhost:5173")
        stripe.api_key = stripe_secret_key

        try:
            checkout_session = stripe.checkout.Session.create(
                mode="payment",
                customer_email=current_user.email,
                metadata={
                    "addon_id": addon_id,
                    "user_id": current_user.id,
                    "pack_id": pack_id,
                    "count": count,
                    "type": "message_addon",
                },
                line_items=[
                    {
                        "price_data": {
                            "currency": "usd",
                            "product_data": {
                                "name": f"PharmacoAI Message Add-on — {count} messages",
                                "description": f"Purchase {count} additional AI messages for your account. Messages do not expire.",
                            },
                            "unit_amount": price_cents,
                        },
                        "quantity": 1,
                    }
                ],
                success_url=f"{frontend_base_url}/subscribe/success?session_id={{CHECKOUT_SESSION_ID}}&type=addon",
                cancel_url=f"{frontend_base_url}/pharmacist/account?checkout=cancel",
            )
        except Exception as stripe_error:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Could not initialize Stripe checkout: {stripe_error}",
            )

        addon_record["checkout_session_id"] = checkout_session.id
        payload = self._read_payload()
        payload.setdefault("addon_purchases", []).append(addon_record)
        with self._lock:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            with self.file_path.open("w", encoding="utf-8") as file_pointer:
                json.dump(payload, file_pointer, indent=2)

        return SubscriptionCheckoutResponse(
            subscription_id=addon_id,
            checkout_session_id=checkout_session.id,
            checkout_url=checkout_session.url,
        )

    def finalize_addon_checkout(self, session_id: str) -> dict:
        payload = self._read_payload()
        addon_purchases = payload.get("addon_purchases", [])

        for record in addon_purchases:
            if record.get("checkout_session_id") != session_id:
                continue
            if record.get("status") == "active":
                return {"count": int(record["count"]), "pack_id": str(record["pack_id"])}

            record["status"] = "active"
            user_id = str(record["user_id"])
            count = int(record["count"])
            pack_id = str(record["pack_id"])
            self.user_service.add_addon_messages(user_id, count)

            with self._lock:
                self.file_path.parent.mkdir(parents=True, exist_ok=True)
                with self.file_path.open("w", encoding="utf-8") as file_pointer:
                    json.dump(payload, file_pointer, indent=2)

            return {"count": count, "pack_id": pack_id}

        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Addon purchase not found")

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
