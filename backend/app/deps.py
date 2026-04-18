from __future__ import annotations

from pathlib import Path

from .agents_service import AgentsService
from .repository import UserRepository
from .service import UserService

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_PATH = BASE_DIR / "data" / "users.json"

_repository = UserRepository(DATA_PATH)
_service = UserService(_repository)
_agents_service = AgentsService()


def get_user_service() -> UserService:
    return _service


def get_agents_service() -> AgentsService:
    return _agents_service
