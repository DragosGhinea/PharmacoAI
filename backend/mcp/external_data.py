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
RXNORM_APPROX_URL = "https://rxnav.nlm.nih.gov/REST/approximateTerm.json"
RXNORM_PROPERTIES_URL = "https://rxnav.nlm.nih.gov/REST/rxcui/{rxcui}/properties.json"
DAILYMED_SPLS_URL = "https://dailymed.nlm.nih.gov/dailymed/services/v2/spls.json"
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


def _clean_term(value: str) -> str:
    return re.sub(r"[^a-z0-9\s]+", " ", _normalize_query(value))


def _base_term(value: str) -> str:
    base = _clean_term(value)
    for suffix in [" sodium", " sodic", " de sodiu", " hydrochloride", " hcl", " potassium", " calcium"]:
        if base.endswith(suffix):
            base = base[: -len(suffix)].strip()
    return base


def _result_matches_terms(record: dict[str, Any], terms: list[str]) -> bool:
    hay = []
    hay.extend(_extract_openfda_list(record, "generic_name"))
    hay.extend(_extract_openfda_list(record, "brand_name"))
    hay.extend(_extract_openfda_list(record, "substance_name"))
    haystack = " ".join(_clean_term(item) for item in hay if str(item).strip())
    if not haystack:
        return False

    for term in terms:
        raw = str(term).strip()
        if not raw:
            continue
        full = _clean_term(raw)
        base = _base_term(raw)
        if full and len(full) < 4:
            full = ""
        if base and len(base) < 4:
            base = ""
        if full and full in haystack:
            return True
        if base and base in haystack:
            return True
    return False


def _rxnorm_matches(name: str) -> tuple[list[str], list[str]]:
    token = _normalize_query(name)
    if not token:
        return [], []

    url = f"{RXNORM_APPROX_URL}?term={quote_plus(token)}&maxEntries=3"
    try:
        with urlopen(url, timeout=DEFAULT_TIMEOUT_SECONDS) as response:
            raw = response.read().decode("utf-8")
        payload = json.loads(raw)
    except Exception:
        return [], []

    candidates = payload.get("approximateGroup", {}).get("candidate", [])
    if not isinstance(candidates, list):
        return [], []

    names: list[str] = []
    rxcuis: list[str] = []
    for item in candidates:
        if not isinstance(item, dict):
            continue
        candidate = str(item.get("candidate", "")).strip().lower()
        rxcui = str(item.get("rxcui", "")).strip()
        if candidate and candidate not in names:
            names.append(candidate)
        if rxcui and rxcui not in rxcuis:
            rxcuis.append(rxcui)
    return names, rxcuis


def _rxnorm_rxcui_names(rxcui: str) -> list[str]:
    token = str(rxcui).strip()
    if not token:
        return []

    url = RXNORM_PROPERTIES_URL.format(rxcui=quote_plus(token))
    try:
        with urlopen(url, timeout=DEFAULT_TIMEOUT_SECONDS) as response:
            raw = response.read().decode("utf-8")
        payload = json.loads(raw)
    except Exception:
        return []

    props = payload.get("properties")
    if not isinstance(props, dict):
        return []

    names: list[str] = []
    for key in ["name", "synonym"]:
        value = props.get(key)
        if isinstance(value, str) and value.strip():
            names.append(value.strip().lower())
    return list(dict.fromkeys(names))


def _query_dailymed(name: str) -> dict[str, Any] | None:
    token = _normalize_query(name)
    if not token:
        return None

    url = f"{DAILYMED_SPLS_URL}?drug_name={quote_plus(token)}"
    try:
        with urlopen(url, timeout=DEFAULT_TIMEOUT_SECONDS) as response:
            raw = response.read().decode("utf-8")
        payload = json.loads(raw)
    except Exception:
        return None

    data = payload.get("data")
    if not isinstance(data, list) or not data:
        return None

    first = data[0]
    if not isinstance(first, dict):
        return None

    set_id = str(first.get("setid", "")).strip()
    title = str(first.get("title", "")).strip()
    if not title:
        return None

    canonical = _normalize_query(title)
    return {
        "source": "dailymed",
        "drug_id": _to_id(canonical),
        "canonical_name": canonical,
        "aliases": [],
        "ingredients": [canonical],
        "indications": [],
        "dosage_form": "unknown",
        "pharmacologic_class": "unknown",
        "contraindications": [],
        "interactions": [],
        "warnings": [],
        "dosage": [],
        "patient_leaflet": title,
        "evidence": {
            "label": [title],
            "contraindications": [],
            "interactions": [],
        },
        "source_links": [
            f"https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid={set_id}" if set_id else ""
        ],
    }


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

    searches: list[str] = []
    # Use OR semantics across generic/brand to avoid over-constrained no-match queries.
    searches.append(f'(openfda.generic_name:"{query}"+OR+openfda.brand_name:"{query}")')
    searches.append(f'openfda.substance_name:"{query}"')

    results: list[dict[str, Any]] | None = None
    for search in searches:
        candidate_results = _query_openfda(search, 1)
        if candidate_results is not None and _result_matches_terms(candidate_results[0], [query]):
            results = candidate_results
            break

    # Fall back to RxNorm-assisted retries only if direct search fails.
    if results is None:
        rxnorm_names, rxnorm_rxcuis = _rxnorm_matches(query)
        fallback_searches: list[str] = []
        for rxcui in rxnorm_rxcuis:
            fallback_searches.append(f'openfda.rxcui:"{rxcui}"')
            for rxnorm_name in _rxnorm_rxcui_names(rxcui):
                fallback_searches.append(f'(openfda.generic_name:"{rxnorm_name}"+OR+openfda.brand_name:"{rxnorm_name}")')
                fallback_searches.append(f'openfda.substance_name:"{rxnorm_name}"')
        for term in rxnorm_names:
            fallback_searches.append(f'(openfda.generic_name:"{term}"+OR+openfda.brand_name:"{term}")')
            fallback_searches.append(f'openfda.substance_name:"{term}"')

        relevance_terms = [query, *rxnorm_names]
        for rxcui in rxnorm_rxcuis:
            relevance_terms.extend(_rxnorm_rxcui_names(rxcui))

        for search in list(dict.fromkeys(fallback_searches)):
            candidate_results = _query_openfda(search, 1)
            if candidate_results is None:
                continue
            if _result_matches_terms(candidate_results[0], relevance_terms):
                results = candidate_results
                break

    if results is None:
        dailymed_terms = [query]
        rxnorm_names, rxnorm_rxcuis = _rxnorm_matches(query)
        dailymed_terms.extend(rxnorm_names)
        for rxcui in rxnorm_rxcuis:
            dailymed_terms.extend(_rxnorm_rxcui_names(rxcui))

        for term in list(dict.fromkeys([_normalize_query(item) for item in dailymed_terms if str(item).strip()])):
            dailymed_result = _query_dailymed(term)
            if dailymed_result is not None:
                if ttl_seconds > 0:
                    with _CACHE_LOCK:
                        _FACTS_CACHE[query] = (_now() + ttl_seconds, dict(dailymed_result))
                return dailymed_result

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
