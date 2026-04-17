from __future__ import annotations

import json
from pathlib import Path
from threading import Lock

from .schemas import UserRecord


class UserRepository:
    def __init__(self, file_path: Path) -> None:
        self.file_path = file_path
        self._lock = Lock()

    def list_users(self) -> list[UserRecord]:
        data = self._read_data()
        return [UserRecord.model_validate(item) for item in data.get("users", [])]

    def save_users(self, users: list[UserRecord]) -> None:
        payload = {"users": [user.model_dump(mode="json") for user in users]}
        with self._lock:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            with self.file_path.open("w", encoding="utf-8") as fp:
                json.dump(payload, fp, indent=2)

    def _read_data(self) -> dict:
        if not self.file_path.exists():
            return {"users": []}
        with self.file_path.open("r", encoding="utf-8") as fp:
            content = fp.read().strip()
            if not content:
                return {"users": []}
            return json.loads(content)
