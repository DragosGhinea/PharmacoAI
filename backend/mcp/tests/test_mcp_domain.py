from __future__ import annotations

from backend.mcp.data import get_record_by_any_name
from backend.mcp.safety import collect_context_gaps, warning_from_context_gaps


def test_normalize_brand_name_to_canonical() -> None:
    record, confidence, matched = get_record_by_any_name("Advil")
    assert record is not None
    assert record.drug_id == "ibuprofen"
    assert confidence >= 0.9
    assert matched == "advil"


def test_collect_context_gaps_identifies_missing_fields() -> None:
    gaps = collect_context_gaps({"age": 34, "sex": "female"})
    assert "pregnancy_or_breastfeeding" in gaps["required_missing"]
    assert gaps["completeness"] < 1.0


def test_warning_generated_when_context_is_incomplete() -> None:
    warnings = warning_from_context_gaps({"age": 50}, "check_interactions")
    assert len(warnings) == 1
    assert warnings[0]["code"] == "MISSING_CONTEXT"
