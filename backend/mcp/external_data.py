from __future__ import annotations

import json
import os
import re
import threading
import time
from typing import Any
from urllib.parse import quote_plus
from urllib.request import urlopen

OPENFDA_BASE = "https://api.fda.gov/drug/label.json"
DEFAULT_TIMEOUT_SECONDS = 7
DEFAULT_CACHE_TTL_SECONDS = 300

_CACHE_LOCK = threading.Lock()
_FACTS_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


def _now() -> float:
    return time.monotonic()


def _cache_ttl_seconds() -> int:
    raw = os.getenv("MCP_OPENFDA_CACHE_TTL_SECONDS", str(DEFAULT_CACHE_TTL_SECONDS))
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_CACHE_TTL_SECONDS

    return max(0, value)


def _normalize_query(name: str) -> str:
    return " ".join(name.strip().lower().split())


def clear_openfda_cache() -> None:
    with _CACHE_LOCK:
        _FACTS_CACHE.clear()


def _extract_first_list_item(payload: dict[str, Any], key: str) -> list[str]:
    value = payload.get(key)
    if not isinstance(value, list):
        return []
    if not value:
        return []

    first = value[0]
    if isinstance(first, str):
        lines = [line.strip() for line in re.split(r"\n+", first) if line.strip()]
        return lines[:8]

    if isinstance(first, list):
        return [str(item).strip() for item in first if str(item).strip()][:8]

    return []


def _extract_openfda_list(payload: dict[str, Any], key: str) -> list[str]:
    openfda = payload.get("openfda", {})
    if not isinstance(openfda, dict):
        return []
    value = openfda.get(key)
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _to_id(name: str) -> str:
    token = re.sub(r"[^a-z0-9]+", "-", name.strip().lower())
    return token.strip("-") or "unknown-drug"


def _query_openfda(search: str, limit: int) -> list[dict[str, Any]] | None:
    encoded = quote_plus(search)
    url = f"{OPENFDA_BASE}?search={encoded}&limit={limit}"

    try:
        with urlopen(url, timeout=DEFAULT_TIMEOUT_SECONDS) as response:
            raw = response.read().decode("utf-8")
        payload = json.loads(raw)
    except Exception:
        return None

    results = payload.get("results")
    if not isinstance(results, list) or not results:
        return None

    parsed = [item for item in results if isinstance(item, dict)]
    return parsed or None


def fetch_openfda_facts(name: str) -> dict[str, Any] | None:
    query = _normalize_query(name)
    if not query:
        return None

    ttl_seconds = _cache_ttl_seconds()
    if ttl_seconds > 0:
        with _CACHE_LOCK:
            entry = _FACTS_CACHE.get(query)
            if entry is not None:
                expires_at, cached_payload = entry
                if expires_at > _now():
                    return dict(cached_payload)
                _FACTS_CACHE.pop(query, None)

    results = _query_openfda(f'openfda.generic_name:"{query}"+openfda.brand_name:"{query}"', 1)
    if results is None:
        return None

    first = results[0]

    generic_names = _extract_openfda_list(first, "generic_name")
    brand_names = _extract_openfda_list(first, "brand_name")
    ingredients = _extract_openfda_list(first, "substance_name") or generic_names

    canonical_name = (generic_names[0] if generic_names else (brand_names[0] if brand_names else query)).lower()
    drug_id = _to_id(canonical_name)

    indications = _extract_first_list_item(first, "indications_and_usage")
    contraindications = _extract_first_list_item(first, "contraindications")
    interactions = _extract_first_list_item(first, "drug_interactions")
    warnings = _extract_first_list_item(first, "warnings")
    dosage = _extract_first_list_item(first, "dosage_and_administration")

    dosage_form = "unknown"
    route = _extract_openfda_list(first, "route")
    if route:
        dosage_form = route[0].lower()

    result = {
        "source": "openfda",
        "drug_id": drug_id,
        "canonical_name": canonical_name,
        "aliases": [item.lower() for item in brand_names],
        "ingredients": [item.lower() for item in ingredients],
        "indications": indications,
        "dosage_form": dosage_form,
        "pharmacologic_class": "unknown",
        "contraindications": contraindications,
        "interactions": interactions,
        "warnings": warnings,
        "dosage": dosage,
        "patient_leaflet": " ".join((warnings[:2] or indications[:2]))[:600],
        "evidence": {
            "label": indications[:3] + warnings[:2],
            "contraindications": contraindications[:4],
            "interactions": interactions[:4],
        },
    }

    if ttl_seconds > 0:
        with _CACHE_LOCK:
            _FACTS_CACHE[query] = (_now() + ttl_seconds, dict(result))

    return result


def fetch_openfda_related_medications(name: str, *, limit: int = 5) -> list[dict[str, Any]]:
    base = fetch_openfda_facts(name)
    if base is None:
        return []

    canonical = str(base.get("canonical_name", "")).lower()
    if not canonical:
        return []

    # Try class-based discovery first and fall back to generic-name neighborhood.
    class_results = _query_openfda(f'openfda.pharm_class_epc:"{canonical}"', limit)
    if class_results is None:
        class_results = _query_openfda(f'openfda.generic_name:"{canonical}"', limit)
    if class_results is None:
        return []

    seen: set[str] = {canonical}
    related: list[dict[str, Any]] = []
    for item in class_results:
        generic_names = _extract_openfda_list(item, "generic_name")
        ingredients = _extract_openfda_list(item, "substance_name") or generic_names
        candidate = (generic_names[0] if generic_names else "").strip().lower()
        if not candidate or candidate in seen:
            continue

        seen.add(candidate)
        related.append(
            {
                "drug_id": _to_id(candidate),
                "canonical_name": candidate,
                "pharmacologic_class": "unknown",
                "ingredients": [part.lower() for part in ingredients],
                "source": "openfda",
            }
        )
        if len(related) >= limit:
            break

    return related
