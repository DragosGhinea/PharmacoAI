from __future__ import annotations

import json

from backend.mcp import external_data


class _FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


def _sample_openfda_payload() -> dict[str, object]:
    return {
        "results": [
            {
                "openfda": {
                    "generic_name": ["Ibuprofen"],
                    "brand_name": ["Advil"],
                    "substance_name": ["Ibuprofen"],
                    "route": ["ORAL"],
                },
                "indications_and_usage": ["Relieves pain and fever"],
                "contraindications": ["Avoid if allergic to NSAIDs"],
                "drug_interactions": ["May interact with warfarin"],
                "warnings": ["May cause stomach bleeding"],
                "dosage_and_administration": ["Use lowest effective dose"],
            }
        ]
    }


def test_fetch_openfda_facts_parses_payload(monkeypatch) -> None:
    external_data.clear_openfda_cache()

    def fake_urlopen(url: str, timeout: int = 0):
        assert "ibuprofen" in url.lower()
        assert timeout == external_data.DEFAULT_TIMEOUT_SECONDS
        return _FakeResponse(_sample_openfda_payload())

    monkeypatch.setenv("MCP_OPENFDA_CACHE_TTL_SECONDS", "0")
    monkeypatch.setattr(external_data, "urlopen", fake_urlopen)

    result = external_data.fetch_openfda_facts("ibuprofen")

    assert result is not None
    assert result["source"] == "openfda"
    assert result["drug_id"] == "ibuprofen"
    assert result["canonical_name"] == "ibuprofen"
    assert result["dosage_form"] == "oral"
    assert "warfarin" in " ".join(result["interactions"]).lower()


def test_fetch_openfda_facts_uses_cache_when_ttl_active(monkeypatch) -> None:
    external_data.clear_openfda_cache()

    calls = {"count": 0}

    def fake_urlopen(url: str, timeout: int = 0):
        calls["count"] += 1
        return _FakeResponse(_sample_openfda_payload())

    monkeypatch.setenv("MCP_OPENFDA_CACHE_TTL_SECONDS", "600")
    monkeypatch.setattr(external_data, "urlopen", fake_urlopen)

    first = external_data.fetch_openfda_facts("Ibuprofen")
    second = external_data.fetch_openfda_facts(" ibuprofen ")

    assert first is not None and second is not None
    assert calls["count"] == 1


def test_fetch_openfda_facts_reloads_after_cache_expiry(monkeypatch) -> None:
    external_data.clear_openfda_cache()

    calls = {"count": 0}
    clock = {"t": 100.0}

    def fake_now() -> float:
        return clock["t"]

    def fake_urlopen(url: str, timeout: int = 0):
        calls["count"] += 1
        return _FakeResponse(_sample_openfda_payload())

    monkeypatch.setenv("MCP_OPENFDA_CACHE_TTL_SECONDS", "10")
    monkeypatch.setattr(external_data, "_now", fake_now)
    monkeypatch.setattr(external_data, "urlopen", fake_urlopen)

    first = external_data.fetch_openfda_facts("ibuprofen")
    clock["t"] = 109.0
    second = external_data.fetch_openfda_facts("ibuprofen")
    clock["t"] = 111.0
    third = external_data.fetch_openfda_facts("ibuprofen")

    assert first is not None and second is not None and third is not None
    assert calls["count"] == 2


def test_fetch_openfda_related_medications_returns_distinct_candidates(monkeypatch) -> None:
    external_data.clear_openfda_cache()

    def fake_query(search: str, limit: int):
        if "generic_name" in search and "brand_name" in search:
            return [
                {
                    "openfda": {
                        "generic_name": ["Ibuprofen"],
                        "brand_name": ["Advil"],
                        "substance_name": ["Ibuprofen"],
                    },
                    "indications_and_usage": ["Relieves pain"],
                }
            ]

        return [
            {
                "openfda": {
                    "generic_name": ["Naproxen"],
                    "substance_name": ["Naproxen"],
                }
            },
            {
                "openfda": {
                    "generic_name": ["Ibuprofen"],
                    "substance_name": ["Ibuprofen"],
                }
            },
        ]

    monkeypatch.setattr(external_data, "_query_openfda", fake_query)
    monkeypatch.setenv("MCP_OPENFDA_CACHE_TTL_SECONDS", "0")

    related = external_data.fetch_openfda_related_medications("ibuprofen", limit=5)
    assert len(related) == 1
    assert related[0]["canonical_name"] == "naproxen"
    assert related[0]["source"] == "openfda"


def test_fetch_openfda_facts_uses_rxnorm_rxcui_fallback(monkeypatch) -> None:
    external_data.clear_openfda_cache()

    searches: list[str] = []

    def fake_rxnorm_matches(_name: str) -> tuple[list[str], list[str]]:
        return ["levothyroxine"], ["8617"]

    def fake_query(search: str, limit: int):
        searches.append(search)
        if "openfda.rxcui" in search:
            return [
                {
                    "openfda": {
                        "generic_name": ["Levothyroxine"],
                        "brand_name": ["Euthyrox"],
                        "substance_name": ["Levothyroxine sodium"],
                        "route": ["ORAL"],
                    },
                    "indications_and_usage": ["Thyroid hormone replacement"],
                }
            ]
        return None

    monkeypatch.setattr(external_data, "_rxnorm_matches", fake_rxnorm_matches)
    monkeypatch.setattr(external_data, "_query_openfda", fake_query)
    monkeypatch.setenv("MCP_OPENFDA_CACHE_TTL_SECONDS", "0")

    result = external_data.fetch_openfda_facts("eutyrox")

    assert result is not None
    assert result["canonical_name"] == "levothyroxine"
    assert any("openfda.rxcui" in item for item in searches)
