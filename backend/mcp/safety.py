from __future__ import annotations

from typing import Any

CRITICAL_CONTEXT_FIELDS: tuple[str, ...] = (
    "age",
    "sex",
    "pregnancy_or_breastfeeding",
    "kidney_disease",
    "liver_disease",
    "allergies",
    "current_medications",
    "dose",
    "frequency",
    "indication",
)

RECOMMENDED_CONTEXT_FIELDS: tuple[str, ...] = (
    "weight_kg",
    "recent_lab_flags",
)


def collect_context_gaps(context: dict[str, Any]) -> dict[str, Any]:
    required_missing = [
        field for field in CRITICAL_CONTEXT_FIELDS if _is_missing(context.get(field))
    ]
    recommended_missing = [
        field for field in RECOMMENDED_CONTEXT_FIELDS if _is_missing(context.get(field))
    ]

    completeness = (
        len(CRITICAL_CONTEXT_FIELDS) - len(required_missing)
    ) / len(CRITICAL_CONTEXT_FIELDS)

    return {
        "required_missing": required_missing,
        "recommended_missing": recommended_missing,
        "completeness": round(completeness, 2),
    }


def warning_from_context_gaps(context: dict[str, Any], capability: str) -> list[dict[str, Any]]:
    gaps = collect_context_gaps(context)
    if not gaps["required_missing"]:
        return []

    return [
        {
            "severity": "warning",
            "code": "MISSING_CONTEXT",
            "capability": capability,
            "message": "Safety analysis is partial because critical context fields are missing.",
            "missing_fields": gaps["required_missing"],
            "recommended_next_action": "Collect missing context before clinical decisions.",
        }
    ]


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) == 0
    return False
