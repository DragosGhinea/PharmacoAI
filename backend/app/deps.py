from __future__ import annotations

from pathlib import Path

from .billing import BillingService
from .repository import UserRepository
from .service import UserService

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_PATH = BASE_DIR / "data" / "users.json"
SUBSCRIPTIONS_PATH = BASE_DIR / "data" / "subscriptions.json"

_repository = UserRepository(DATA_PATH)
_service = UserService(_repository)
_billing_service = BillingService(SUBSCRIPTIONS_PATH, _service)


def get_user_service() -> UserService:
    return _service


def get_billing_service() -> BillingService:
    return _billing_service
