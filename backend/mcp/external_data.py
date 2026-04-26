from __future__ import annotations

import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any
from urllib.parse import quote, quote_plus
from urllib.request import urlopen

OPENFDA_BASE = "https://api.fda.gov/drug/label.json"
RXNORM_APPROX_URL = "https://rxnav.nlm.nih.gov/REST/approximateTerm.json"
RXNORM_PROPERTIES_URL = "https://rxnav.nlm.nih.gov/REST/rxcui/{rxcui}/properties.json"
DAILYMED_SPLS_URL = "https://dailymed.nlm.nih.gov/dailymed/services/v2/spls.json"
PUBCHEM_CID_BY_NAME_URL = "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{name}/cids/JSON"
PUBCHEM_PROPERTIES_URL = (
    "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid}/property/Title,IUPACName,InChIKey/JSON"
)
PUBCHEM_SYNONYMS_URL = "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid}/synonyms/JSON"
CHEMBL_SEARCH_URL = "https://www.ebi.ac.uk/chembl/api/data/molecule/search"
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


def _fetch_json(url: str) -> dict[str, Any] | None:
    try:
        with urlopen(url, timeout=DEFAULT_TIMEOUT_SECONDS) as response:
            raw = response.read().decode("utf-8")
        payload = json.loads(raw)
    except Exception:
        return None

    return payload if isinstance(payload, dict) else None


def _extract_openfda_identifiers(record: dict[str, Any]) -> dict[str, Any]:
    openfda = record.get("openfda", {})
    if not isinstance(openfda, dict):
        return {}

    identifiers: dict[str, Any] = {}
    for key in ["rxcui", "unii", "spl_set_id", "spl_id", "application_number", "product_ndc"]:
        value = openfda.get(key)
        if isinstance(value, list) and value:
            identifiers[key] = [str(item).strip() for item in value if str(item).strip()]

    return identifiers


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
        "identifiers": _extract_openfda_identifiers(first),
        "source_links": [f"{OPENFDA_BASE}?search={quote_plus(f'openfda.generic_name:\"{canonical_name}\"')}&limit=1"],
    }

    if ttl_seconds > 0:
        with _CACHE_LOCK:
            _FACTS_CACHE[query] = (_now() + ttl_seconds, dict(result))

    return result


def fetch_pubchem_facts(name: str) -> dict[str, Any] | None:
    query = _normalize_query(name)
    if not query:
        return None

    cid_payload = _fetch_json(PUBCHEM_CID_BY_NAME_URL.format(name=quote(query)))
    if cid_payload is None:
        return None

    cids = cid_payload.get("IdentifierList", {}).get("CID", [])
    if not isinstance(cids, list) or not cids:
        return None

    cid = cids[0]
    properties_payload = _fetch_json(PUBCHEM_PROPERTIES_URL.format(cid=quote(str(cid))))
    if properties_payload is None:
        return None

    props = properties_payload.get("PropertyTable", {}).get("Properties", [])
    if not isinstance(props, list) or not props:
        return None

    first = props[0] if isinstance(props[0], dict) else {}
    title = str(first.get("Title", "")).strip()
    iupac = str(first.get("IUPACName", "")).strip()
    inchi_key = str(first.get("InChIKey", "")).strip()
    canonical = _normalize_query(title or iupac or query)
    if not canonical:
        return None

    aliases: list[str] = []
    synonyms_payload = _fetch_json(PUBCHEM_SYNONYMS_URL.format(cid=quote(str(cid))))
    if synonyms_payload is not None:
        info = synonyms_payload.get("InformationList", {}).get("Information", [])
        if isinstance(info, list) and info and isinstance(info[0], dict):
            synonyms = info[0].get("Synonym", [])
            if isinstance(synonyms, list):
                aliases = [str(item).strip().lower() for item in synonyms[:10] if str(item).strip()]

    return {
        "source": "pubchem",
        "drug_id": _to_id(canonical),
        "canonical_name": canonical,
        "aliases": list(dict.fromkeys(aliases)),
        "ingredients": [canonical],
        "indications": [],
        "dosage_form": "unknown",
        "pharmacologic_class": "unknown",
        "contraindications": [],
        "interactions": [],
        "warnings": [],
        "dosage": [],
        "patient_leaflet": "",
        "evidence": {
            "label": [f"PubChem match for '{canonical}'."],
            "contraindications": [],
            "interactions": [],
        },
        "identifiers": {
            "pubchem_cid": str(cid),
            "inchi_key": inchi_key,
        },
        "source_links": [
            f"https://pubchem.ncbi.nlm.nih.gov/compound/{quote(str(cid))}",
        ],
    }


def fetch_chembl_facts(name: str) -> dict[str, Any] | None:
    query = _normalize_query(name)
    if not query:
        return None

    search_url = f"{CHEMBL_SEARCH_URL}?q={quote_plus(query)}&format=json"
    payload = _fetch_json(search_url)
    if payload is None:
        return None

    molecules = payload.get("molecules", [])
    if not isinstance(molecules, list) or not molecules:
        return None

    first = molecules[0]
    if not isinstance(first, dict):
        return None

    chembl_id = str(first.get("molecule_chembl_id", "")).strip()
    pref_name = str(first.get("pref_name", "")).strip()
    struct = first.get("molecule_structures", {})
    inchi_key = ""
    if isinstance(struct, dict):
        inchi_key = str(struct.get("standard_inchi_key", "")).strip()

    synonyms = first.get("molecule_synonyms", [])
    aliases: list[str] = []
    if isinstance(synonyms, list):
        for item in synonyms[:10]:
            if not isinstance(item, dict):
                continue
            token = str(item.get("molecule_synonym", "")).strip().lower()
            if token:
                aliases.append(token)

    canonical = _normalize_query(pref_name or query)
    if not canonical:
        return None

    return {
        "source": "chembl",
        "drug_id": _to_id(canonical),
        "canonical_name": canonical,
        "aliases": list(dict.fromkeys(aliases)),
        "ingredients": [canonical],
        "indications": [],
        "dosage_form": "unknown",
        "pharmacologic_class": "unknown",
        "contraindications": [],
        "interactions": [],
        "warnings": [],
        "dosage": [],
        "patient_leaflet": "",
        "evidence": {
            "label": [f"ChEMBL molecule search match for '{canonical}'."],
            "contraindications": [],
            "interactions": [],
        },
        "identifiers": {
            "chembl_id": chembl_id,
            "inchi_key": inchi_key,
        },
        "source_links": [
            f"https://www.ebi.ac.uk/chembl/compound_report_card/{quote(chembl_id)}/"
            if chembl_id
            else ""
        ],
    }


def _default_source_priority() -> list[str]:
    raw = os.getenv("MCP_DATA_SOURCE_PRIORITY", "openfda,pubchem,chembl")
    order = [_normalize_query(item) for item in raw.split(",") if item.strip()]
    allowed = {"openfda", "pubchem", "chembl"}
    filtered: list[str] = []
    for source in order:
        if source in allowed and source not in filtered:
            filtered.append(source)
    if not filtered:
        return ["openfda", "pubchem", "chembl"]
    return filtered


def _dedupe_str_list(values: list[str]) -> list[str]:
    output: list[str] = []
    for value in values:
        token = str(value).strip()
        if token and token not in output:
            output.append(token)
    return output


def _merge_identifiers(payloads: list[dict[str, Any]]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for payload in payloads:
        identifiers = payload.get("identifiers", {})
        if not isinstance(identifiers, dict):
            continue
        for key, value in identifiers.items():
            if value in (None, "", []):
                continue
            existing = merged.get(key)
            if existing is None:
                merged[key] = value
                continue

            existing_list = existing if isinstance(existing, list) else [existing]
            incoming_list = value if isinstance(value, list) else [value]
            combined = _dedupe_str_list([str(item) for item in [*existing_list, *incoming_list]])
            merged[key] = combined if len(combined) > 1 else combined[0]

    return merged


def _merge_facts_payloads(found: list[dict[str, Any]], source_priority: list[str]) -> dict[str, Any]:
    def _priority_index(source: str) -> int:
        try:
            return source_priority.index(source)
        except ValueError:
            return len(source_priority)

    ranked = sorted(
        found,
        key=lambda payload: _priority_index(str(payload.get("source", "")).lower()),
    )
    primary = ranked[0]

    aliases: list[str] = []
    ingredients: list[str] = []
    indications: list[str] = []
    contraindications: list[str] = []
    warnings: list[str] = []
    dosage: list[str] = []
    source_links: list[str] = []
    interactions: list[str] = []
    evidence = {
        "label": [],
        "contraindications": [],
        "interactions": [],
    }

    for payload in ranked:
        aliases.extend(payload.get("aliases", []))
        ingredients.extend(payload.get("ingredients", []))
        indications.extend(payload.get("indications", []))
        contraindications.extend(payload.get("contraindications", []))
        warnings.extend(payload.get("warnings", []))
        dosage.extend(payload.get("dosage", []))
        source_links.extend(payload.get("source_links", []))

        payload_interactions = payload.get("interactions", [])
        if isinstance(payload_interactions, list):
            interactions.extend(payload_interactions)

        payload_evidence = payload.get("evidence", {})
        if isinstance(payload_evidence, dict):
            for key in ["label", "contraindications", "interactions"]:
                section = payload_evidence.get(key, [])
                if isinstance(section, list):
                    evidence[key].extend(section)

    pharmacologic_class = "unknown"
    dosage_form = "unknown"
    for payload in ranked:
        candidate_class = str(payload.get("pharmacologic_class", "")).strip()
        if candidate_class and candidate_class != "unknown":
            pharmacologic_class = candidate_class
            break
    for payload in ranked:
        candidate_form = str(payload.get("dosage_form", "")).strip()
        if candidate_form and candidate_form != "unknown":
            dosage_form = candidate_form
            break

    sources = _dedupe_str_list([str(payload.get("source", "")).strip() for payload in ranked])
    merged = {
        "source": "aggregated" if len(sources) > 1 else (sources[0] if sources else "unknown"),
        "sources": sources,
        "source_results": ranked,
        "drug_id": primary.get("drug_id", _to_id(str(primary.get("canonical_name", "")))),
        "canonical_name": primary.get("canonical_name", ""),
        "aliases": _dedupe_str_list([str(item).lower() for item in aliases]),
        "ingredients": _dedupe_str_list([str(item).lower() for item in ingredients]),
        "indications": _dedupe_str_list([str(item).strip() for item in indications]),
        "dosage_form": dosage_form,
        "pharmacologic_class": pharmacologic_class,
        "contraindications": _dedupe_str_list([str(item).strip() for item in contraindications]),
        "interactions": _dedupe_str_list([str(item).strip() for item in interactions]),
        "warnings": _dedupe_str_list([str(item).strip() for item in warnings]),
        "dosage": _dedupe_str_list([str(item).strip() for item in dosage]),
        "patient_leaflet": str(primary.get("patient_leaflet", "")),
        "evidence": {
            "label": _dedupe_str_list([str(item).strip() for item in evidence["label"]]),
            "contraindications": _dedupe_str_list([str(item).strip() for item in evidence["contraindications"]]),
            "interactions": _dedupe_str_list([str(item).strip() for item in evidence["interactions"]]),
        },
        "identifiers": _merge_identifiers(ranked),
        "source_links": _dedupe_str_list([str(item).strip() for item in source_links if str(item).strip()]),
    }
    return merged


def fetch_medication_facts(name: str, *, source_priority: list[str] | None = None) -> dict[str, Any] | None:
    query = _normalize_query(name)
    if not query:
        return None

    handlers = {
        "openfda": fetch_openfda_facts,
        "pubchem": fetch_pubchem_facts,
        "chembl": fetch_chembl_facts,
    }
    priority = source_priority or _default_source_priority()
    tasks: list[tuple[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, len(priority))) as pool:
        for source in priority:
            handler = handlers.get(source)
            if handler is None:
                continue
            tasks.append((source, pool.submit(handler, query)))

        found: list[dict[str, Any]] = []
        future_to_source = {future: source for source, future in tasks}
        for future in as_completed(future_to_source):
            source = future_to_source[future]
            try:
                payload = future.result()
            except Exception:
                payload = None
            if not isinstance(payload, dict):
                continue
            if not payload.get("source"):
                payload["source"] = source
            found.append(payload)

    if not found:
        return None

    return _merge_facts_payloads(found, priority)


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
                "relation_type": "therapeutic-class-neighborhood",
            }
        )
        if len(related) >= limit:
            break

    return related


def fetch_pubchem_related_medications(name: str, *, limit: int = 5) -> list[dict[str, Any]]:
    base = fetch_pubchem_facts(name)
    if base is None:
        return []

    canonical = str(base.get("canonical_name", "")).strip().lower()
    if not canonical:
        return []

    related: list[dict[str, Any]] = []
    seen: set[str] = {canonical}
    for alias in base.get("aliases", []):
        token = _normalize_query(str(alias))
        if not token or token in seen:
            continue
        if len(token) < 4:
            continue

        seen.add(token)
        related.append(
            {
                "drug_id": _to_id(token),
                "canonical_name": token,
                "pharmacologic_class": "unknown",
                "ingredients": [canonical],
                "source": "pubchem",
                "relation_type": "synonym-neighborhood",
            }
        )
        if len(related) >= limit:
            break

    return related


def fetch_chembl_related_medications(name: str, *, limit: int = 5) -> list[dict[str, Any]]:
    base = fetch_chembl_facts(name)
    if base is None:
        return []

    canonical = str(base.get("canonical_name", "")).strip().lower()
    if not canonical:
        return []

    related: list[dict[str, Any]] = []
    seen: set[str] = {canonical}
    for alias in base.get("aliases", []):
        token = _normalize_query(str(alias))
        if not token or token in seen:
            continue
        if len(token) < 4:
            continue

        seen.add(token)
        related.append(
            {
                "drug_id": _to_id(token),
                "canonical_name": token,
                "pharmacologic_class": "unknown",
                "ingredients": [canonical],
                "source": "chembl",
                "relation_type": "synonym-neighborhood",
            }
        )
        if len(related) >= limit:
            break

    return related


def fetch_related_medications(
    name: str,
    *,
    limit: int = 5,
    source_priority: list[str] | None = None,
) -> dict[str, Any]:
    query = _normalize_query(name)
    if not query:
        return {"related": [], "sources": [], "source_results": []}

    handlers = {
        "openfda": fetch_openfda_related_medications,
        "pubchem": fetch_pubchem_related_medications,
        "chembl": fetch_chembl_related_medications,
    }
    priority = source_priority or _default_source_priority()

    tasks: list[tuple[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, len(priority))) as pool:
        for source in priority:
            handler = handlers.get(source)
            if handler is None:
                continue
            tasks.append((source, pool.submit(handler, query, limit=limit)))

        per_source: dict[str, list[dict[str, Any]]] = {}
        future_to_source = {future: source for source, future in tasks}
        for future in as_completed(future_to_source):
            source = future_to_source[future]
            try:
                items = future.result()
            except Exception:
                items = []

            normalized_items: list[dict[str, Any]] = []
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict):
                        normalized_items.append(item)
            per_source[source] = normalized_items

    ranked_sources = [source for source in priority if source in per_source]
    merged: list[dict[str, Any]] = []
    seen_names: set[str] = set()

    for source in ranked_sources:
        for item in per_source[source]:
            canonical = _normalize_query(str(item.get("canonical_name", "")))
            if not canonical or canonical in seen_names:
                continue
            seen_names.add(canonical)
            merged.append(item)

    source_results = [{"source": source, "items": per_source.get(source, [])} for source in ranked_sources]
    matched_sources = [source for source in ranked_sources if per_source.get(source)]

    capped = merged[:limit]
    therapeutic_alternatives: list[dict[str, Any]] = []
    synonym_or_name_neighbors: list[dict[str, Any]] = []
    for item in capped:
        relation_type = str(item.get("relation_type", "")).strip().lower()
        if relation_type.startswith("synonym") or relation_type.startswith("name"):
            synonym_or_name_neighbors.append(item)
        else:
            therapeutic_alternatives.append(item)

    return {
        "related": capped,
        "therapeutic_alternatives": therapeutic_alternatives,
        "synonym_or_name_neighbors": synonym_or_name_neighbors,
        "sources": matched_sources,
        "source_results": source_results,
    }
