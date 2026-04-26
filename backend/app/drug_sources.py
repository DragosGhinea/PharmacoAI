from __future__ import annotations

import os
import re
import time
from typing import Any

import httpx

OPENFDA_LABEL_URL = "https://api.fda.gov/drug/label.json"
RXNORM_APPROX_URL = "https://rxnav.nlm.nih.gov/REST/approximateTerm.json"
DAILYMED_SPLS_URL = "https://dailymed.nlm.nih.gov/dailymed/services/v2/spls.json"

_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


def _cache_ttl_seconds() -> int:
    raw = os.getenv("DRUG_SOURCES_CACHE_TTL_SECONDS", "300")
    try:
        return max(0, int(raw))
    except ValueError:
        return 300


def _normalize_key(name: str) -> str:
    return " ".join(name.lower().strip().split())


def _extract_first_lines(record: dict[str, Any], key: str, limit: int = 3) -> list[str]:
    section = record.get(key)
    if not isinstance(section, list) or not section:
        return []
    first = section[0]
    if not isinstance(first, str):
        return []
    lines = [line.strip() for line in re.split(r"\n+", first) if line.strip()]
    return lines[:limit]


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


async def _rxnorm_normalize(name: str) -> dict[str, Any]:
    params = {"term": name, "maxEntries": 1}
    async with httpx.AsyncClient(timeout=8.0) as client:
        response = await client.get(RXNORM_APPROX_URL, params=params)

    if response.status_code >= 400:
        return {"name": name, "rxcui": None, "score": 0}

    data = response.json()
    candidates = data.get("approximateGroup", {}).get("candidate", [])
    if isinstance(candidates, list) and candidates:
        first = candidates[0]
        return {
            "name": name,
            "rxcui": first.get("rxcui"),
            "score": _safe_float(first.get("score", 0.0)),
        }

    return {"name": name, "rxcui": None, "score": 0}


async def _openfda_label(name: str, rxcui: str | None) -> dict[str, Any]:
    search_parts: list[str] = []
    if rxcui:
        search_parts.append(f'openfda.rxcui:"{rxcui}"')
    search_parts.append(f'openfda.generic_name:"{name}"')
    search_parts.append(f'openfda.brand_name:"{name}"')

    search = "+".join(search_parts)
    params = {"search": search, "limit": 1}

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(OPENFDA_LABEL_URL, params=params)

    if response.status_code >= 400:
        return {
            "record": None,
            "source": "openfda",
            "url": f"{OPENFDA_LABEL_URL}?search={search}&limit=1",
        }

    data = response.json()
    results = data.get("results")
    if not isinstance(results, list) or not results:
        return {
            "record": None,
            "source": "openfda",
            "url": f"{OPENFDA_LABEL_URL}?search={search}&limit=1",
        }

    record = results[0] if isinstance(results[0], dict) else None
    return {
        "record": record,
        "source": "openfda",
        "url": f"{OPENFDA_LABEL_URL}?search={search}&limit=1",
    }


async def _dailymed_lookup(name: str) -> dict[str, Any]:
    params = {"drug_name": name}
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(DAILYMED_SPLS_URL, params=params)

    if response.status_code >= 400:
        return {"spl_set_id": None, "title": None, "url": None}

    data = response.json()
    payload = data.get("data")
    if not isinstance(payload, list) or not payload:
        return {"spl_set_id": None, "title": None, "url": None}

    first = payload[0] if isinstance(payload[0], dict) else {}
    set_id = first.get("setid")
    title = first.get("title")
    page_url = f"https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid={set_id}" if set_id else None
    return {
        "spl_set_id": set_id,
        "title": title,
        "url": page_url,
    }


async def get_grounded_medication_context(name: str) -> dict[str, Any]:
    key = _normalize_key(name)
    ttl = _cache_ttl_seconds()

    if ttl > 0 and key in _CACHE:
        expires_at, payload = _CACHE[key]
        if expires_at > time.monotonic():
            return payload

    rxnorm = await _rxnorm_normalize(name)
    openfda = await _openfda_label(name, rxnorm.get("rxcui"))
    dailymed = await _dailymed_lookup(name)

    record = openfda.get("record")
    indications = _extract_first_lines(record, "indications_and_usage") if isinstance(record, dict) else []
    contraindications = _extract_first_lines(record, "contraindications") if isinstance(record, dict) else []
    interactions = _extract_first_lines(record, "drug_interactions") if isinstance(record, dict) else []
    warnings = _extract_first_lines(record, "warnings") if isinstance(record, dict) else []

    canonical_name = name
    if isinstance(record, dict):
        generic_names = record.get("openfda", {}).get("generic_name", [])
        if isinstance(generic_names, list) and generic_names:
            canonical_name = str(generic_names[0]).lower()

    source_links = [openfda.get("url"), dailymed.get("url")]
    source_links = [item for item in source_links if isinstance(item, str) and item]

    payload = {
        "query": name,
        "canonical_name": canonical_name,
        "rxnorm": rxnorm,
        "sections": {
            "indications": indications,
            "contraindications": contraindications,
            "interactions": interactions,
            "warnings": warnings,
        },
        "source_links": source_links,
        "evidence_snippets": indications[:2] + contraindications[:2] + interactions[:2] + warnings[:2],
        "dailymed": dailymed,
    }

    if ttl > 0:
        _CACHE[key] = (time.monotonic() + ttl, payload)

    return payload
