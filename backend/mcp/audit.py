from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any


LOGGER = logging.getLogger("pharmacoai.mcp.audit")


def setup_audit_logger() -> None:
    if LOGGER.handlers:
        return

    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )
    handler.setFormatter(formatter)
    LOGGER.addHandler(handler)
    LOGGER.setLevel(logging.INFO)


def log_audit(
    capability: str,
    caller_id: str,
    status: str,
    risk_tier: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "capability": capability,
        "caller_id": caller_id,
        "status": status,
        "risk_tier": risk_tier,
        "metadata": metadata or {},
    }
    LOGGER.info(payload)
