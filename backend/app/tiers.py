from __future__ import annotations

from enum import Enum


class Tier(str, Enum):
    FREE = "free"
    PRO = "pro"
    ULTIMATE = "ultimate"


TIER_FEATURES = {
    Tier.FREE: {
        "monthly_message_limit": 50,
        "allowed_agents": ["basic-assistant"],
    },
    Tier.PRO: {
        "monthly_message_limit": 500,
        "allowed_agents": ["basic-assistant", "clinical-analyst"],
    },
    Tier.ULTIMATE: {
        "monthly_message_limit": 2000,
        "allowed_agents": ["basic-assistant", "clinical-analyst", "strategic-advisor"],
    },
}
