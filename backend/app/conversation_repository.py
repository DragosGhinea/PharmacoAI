from __future__ import annotations

import json
from pathlib import Path
from threading import Lock

from .agents_schemas import AgentConversation


class ConversationRepository:
    def __init__(self, file_path: Path) -> None:
        self.file_path = file_path
        self._lock = Lock()

    def list_conversations(self) -> list[AgentConversation]:
        data = self._read_data()
        return [AgentConversation.model_validate(item) for item in data.get("conversations", [])]

    def save_conversations(self, conversations: list[AgentConversation]) -> None:
        payload = {
            "conversations": [
                conversation.model_dump(mode="json", exclude_none=False, exclude_defaults=False)
                for conversation in conversations
            ],
        }
        with self._lock:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            with self.file_path.open("w", encoding="utf-8") as fp:
                json.dump(payload, fp, indent=2)

    def _read_data(self) -> dict:
        if not self.file_path.exists():
            return {"conversations": []}
        with self.file_path.open("r", encoding="utf-8") as fp:
            content = fp.read().strip()
            if not content:
                return {"conversations": []}
            return json.loads(content)
