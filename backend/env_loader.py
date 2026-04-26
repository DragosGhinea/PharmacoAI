from __future__ import annotations

import os
from pathlib import Path

_ROOT_ENV_LOADED = False


def _parse_env_value(raw_value: str) -> str:
    value = raw_value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"\"", "'"}:
        return value[1:-1]
    return value


def load_root_env(*, override: bool = False, filename: str = ".env") -> None:
    """Load repository-root env vars into process environment.

    Existing process variables win by default unless override=True.
    """
    global _ROOT_ENV_LOADED
    if _ROOT_ENV_LOADED:
        return

    root_dir = Path(__file__).resolve().parents[1]
    env_path = root_dir / filename
    if not env_path.exists() or not env_path.is_file():
        _ROOT_ENV_LOADED = True
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if line.startswith("export "):
            line = line[len("export ") :].strip()

        if "=" not in line:
            continue

        key, raw_value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue

        value = _parse_env_value(raw_value)
        if override or key not in os.environ:
            os.environ[key] = value

    _ROOT_ENV_LOADED = True
