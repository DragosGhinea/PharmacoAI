from __future__ import annotations

from enum import Enum


class Tier(str, Enum):
    FREE = "free"
    PRO = "pro"
    ULTIMATE = "ultimate"


TIER_FEATURES = {
    Tier.FREE: {
        "monthly_message_limit": 150,
        "allowed_agents": ["drug-explainer", "ingredient-analyst", "summary-agent"],
        "admin_user_limit": 1,
        "supports_message_addons": True,
        "monthly_price_cents": 1000,
    },
    Tier.PRO: {
        "monthly_message_limit": 3000,
        "allowed_agents": ["drug-explainer", "ingredient-analyst", "summary-agent"],
        "admin_user_limit": 8,
        "supports_message_addons": True,
        "monthly_price_cents": 9900,
    },
    Tier.ULTIMATE: {
        "monthly_message_limit": 20000,
        "allowed_agents": ["drug-explainer", "ingredient-analyst", "summary-agent"],
        "admin_user_limit": 50,
        "supports_message_addons": True,
        "monthly_price_cents": 29900,
    },
}
