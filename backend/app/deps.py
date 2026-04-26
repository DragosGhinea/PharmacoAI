from __future__ import annotations

from pathlib import Path

from .agents_service import AgentsService
from .conversation_repository import ConversationRepository
from .repository import UserRepository
from .service import UserService

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_PATH = BASE_DIR / "data" / "users.json"
CONVERSATIONS_PATH = BASE_DIR / "data" / "conversations.json"

_repository = UserRepository(DATA_PATH)
_service = UserService(_repository)
_conversation_repository = ConversationRepository(CONVERSATIONS_PATH)
_agents_service = AgentsService(conversation_repository=_conversation_repository)


def get_user_service() -> UserService:
    return _service


def get_agents_service() -> AgentsService:
    return _agents_service
