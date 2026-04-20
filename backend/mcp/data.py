from __future__ import annotations

from dataclasses import dataclass
from difflib import get_close_matches
from pathlib import Path
import json
import threading
import unicodedata


@dataclass(frozen=True)
class MedicationRecord:
    drug_id: str
    canonical_name: str
    aliases: tuple[str, ...]
    ingredients: tuple[str, ...]
    indications: tuple[str, ...]
    dosage_form: str
    pharmacologic_class: str
    contraindications: tuple[str, ...]
    interactions: dict[str, dict[str, str]]
    patient_leaflet: str
    evidence: dict[str, tuple[str, ...]]


MEDICATIONS: dict[str, MedicationRecord] = {
    "ibuprofen": MedicationRecord(
        drug_id="ibuprofen",
        canonical_name="ibuprofen",
        aliases=("advil", "motrin", "ibu", "ibuprophen"),
        ingredients=("ibuprofen",),
        indications=("pain", "fever", "inflammation"),
        dosage_form="tablet",
        pharmacologic_class="NSAID",
        contraindications=(
            "active peptic ulcer disease",
            "severe renal impairment",
            "history of NSAID hypersensitivity",
            "third-trimester pregnancy",
        ),
        interactions={
            "warfarin": {
                "severity": "high",
                "message": "Increased bleeding risk when NSAIDs are combined with anticoagulants.",
            },
            "aspirin": {
                "severity": "moderate",
                "message": "Combined use may increase GI irritation and bleeding risk.",
            },
        },
        patient_leaflet=(
            "Take with food to reduce stomach upset. Stop and seek care for black stools,"
            " severe abdominal pain, or signs of allergic reaction."
        ),
        evidence={
            "label": (
                "NSAID class warning includes GI bleeding risk.",
                "Use the lowest effective dose for the shortest duration.",
            ),
            "interactions": (
                "Concomitant anticoagulants may increase bleeding events.",
            ),
            "contraindications": (
                "Avoid in severe renal impairment and in late pregnancy.",
            ),
        },
    ),
    "acetaminophen": MedicationRecord(
        drug_id="acetaminophen",
        canonical_name="acetaminophen",
        aliases=("paracetamol", "tylenol", "acetaminophene"),
        ingredients=("acetaminophen",),
        indications=("pain", "fever"),
        dosage_form="tablet",
        pharmacologic_class="analgesic",
        contraindications=(
            "severe hepatic impairment",
            "known hypersensitivity to acetaminophen",
        ),
        interactions={
            "warfarin": {
                "severity": "moderate",
                "message": "Frequent/high-dose use may increase INR; monitor closely.",
            },
        },
        patient_leaflet=(
            "Do not exceed the maximum daily dose from all products combined."
            " Check labels for hidden acetaminophen."
        ),
        evidence={
            "label": (
                "Hepatotoxicity can occur with overdose.",
                "Track total daily acetaminophen intake across products.",
            ),
            "interactions": (
                "High cumulative dosing with warfarin may increase bleeding tendency.",
            ),
            "contraindications": (
                "Avoid in severe hepatic impairment.",
            ),
        },
    ),
    "warfarin": MedicationRecord(
        drug_id="warfarin",
        canonical_name="warfarin",
        aliases=("coumadin",),
        ingredients=("warfarin",),
        indications=("stroke prevention", "venous thromboembolism"),
        dosage_form="tablet",
        pharmacologic_class="vitamin K antagonist",
        contraindications=(
            "pregnancy",
            "active major bleeding",
        ),
        interactions={
            "ibuprofen": {
                "severity": "high",
                "message": "Major bleeding risk rises when warfarin is combined with NSAIDs.",
            },
            "amoxicillin": {
                "severity": "moderate",
                "message": "Antibiotics can alter INR; monitor and adjust as needed.",
            },
        },
        patient_leaflet=(
            "Requires regular INR monitoring. Report any unusual bleeding immediately."
        ),
        evidence={
            "label": (
                "Warfarin carries boxed warnings for major or fatal bleeding.",
            ),
            "interactions": (
                "Many drugs can raise or lower INR.",
            ),
            "contraindications": (
                "Contraindicated in pregnancy except in specific specialist-managed circumstances.",
            ),
        },
    ),
    "amoxicillin": MedicationRecord(
        drug_id="amoxicillin",
        canonical_name="amoxicillin",
        aliases=("amox",),
        ingredients=("amoxicillin",),
        indications=("bacterial infection"),
        dosage_form="capsule",
        pharmacologic_class="aminopenicillin antibiotic",
        contraindications=(
            "history of severe beta-lactam allergy",
        ),
        interactions={
            "warfarin": {
                "severity": "moderate",
                "message": "May increase INR in some patients; monitor anticoagulation.",
            },
        },
        patient_leaflet=(
            "Complete the full prescribed course. Seek care for severe rash or breathing issues."
        ),
        evidence={
            "label": (
                "Hypersensitivity reactions can be serious in penicillin-allergic patients.",
            ),
            "interactions": (
                "INR changes with anticoagulants have been reported.",
            ),
            "contraindications": (
                "Avoid in known severe beta-lactam hypersensitivity.",
            ),
        },
    ),
    "levothyroxine": MedicationRecord(
        drug_id="levothyroxine",
        canonical_name="levothyroxine",
        aliases=("euthyrox", "eutyrox", "eltroxin", "levotiroxina", "l-thyroxine"),
        ingredients=("levothyroxine sodium",),
        indications=("hypothyroidism", "thyroid hormone replacement", "goiter suppression"),
        dosage_form="tablet",
        pharmacologic_class="thyroid hormone",
        contraindications=(
            "untreated thyrotoxicosis",
            "uncorrected adrenal insufficiency",
            "acute myocardial infarction without specialist supervision",
        ),
        interactions={
            "warfarin": {
                "severity": "moderate",
                "message": "Can enhance anticoagulant effect; monitor INR when dose changes.",
            },
            "ibuprofen": {
                "severity": "low",
                "message": "No major direct interaction, but symptoms and thyroid control should still be monitored.",
            },
        },
        patient_leaflet=(
            "Take on an empty stomach, at the same time each day. "
            "Avoid taking with calcium or iron supplements within 4 hours."
        ),
        evidence={
            "label": (
                "Dose titration should be individualized based on TSH and clinical response.",
                "Absorption can be reduced by calcium, iron, and some antacids.",
            ),
            "interactions": (
                "Monitor anticoagulation when thyroid hormone dose is initiated or changed.",
            ),
            "contraindications": (
                "Avoid in untreated thyrotoxicosis and uncorrected adrenal insufficiency.",
            ),
        },
    ),
    "metamizole": MedicationRecord(
        drug_id="metamizole",
        canonical_name="metamizole",
        aliases=(
            "metamizol",
            "metamizol sodic",
            "metamizol sodium",
            "metamizole sodium",
            "dipyrone",
            "analgin",
            "algocalmin",
        ),
        ingredients=("metamizole sodium", "dipyrone"),
        indications=("acute pain", "colic pain", "fever"),
        dosage_form="tablet",
        pharmacologic_class="pyrazolone analgesic",
        contraindications=(
            "history of metamizole hypersensitivity",
            "history of agranulocytosis",
            "severe bone marrow suppression",
        ),
        interactions={
            "warfarin": {
                "severity": "moderate",
                "message": "May increase bleeding risk in anticoagulated patients; monitor clinically.",
            },
        },
        patient_leaflet=(
            "Use only as directed. Stop and seek urgent care for fever, sore throat, mouth ulcers, "
            "or other infection signs while using metamizole."
        ),
        evidence={
            "label": (
                "Used in some regions as a non-opioid analgesic and antipyretic.",
                "Safety profile requires monitoring for rare but serious blood dyscrasias.",
            ),
            "interactions": (
                "Consider closer monitoring with anticoagulants.",
            ),
            "contraindications": (
                "Avoid in prior agranulocytosis or severe marrow suppression.",
            ),
        },
    ),
}


_ALIAS_CACHE_LOCK = threading.Lock()
_ALIAS_CACHE_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "medication_alias_cache.json"
)
_LEARNED_ALIAS_CACHE: dict[str, str] | None = None


def _load_learned_aliases_unlocked() -> dict[str, str]:
    global _LEARNED_ALIAS_CACHE
    if _LEARNED_ALIAS_CACHE is not None:
        return dict(_LEARNED_ALIAS_CACHE)

    try:
        if _ALIAS_CACHE_PATH.exists():
            payload = json.loads(_ALIAS_CACHE_PATH.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                _LEARNED_ALIAS_CACHE = {
                    normalize_token(str(key)): normalize_token(str(value))
                    for key, value in payload.items()
                    if str(key).strip() and str(value).strip()
                }
            else:
                _LEARNED_ALIAS_CACHE = {}
        else:
            _LEARNED_ALIAS_CACHE = {}
    except Exception:
        _LEARNED_ALIAS_CACHE = {}

    return dict(_LEARNED_ALIAS_CACHE)


def _load_learned_aliases() -> dict[str, str]:
    with _ALIAS_CACHE_LOCK:
        return _load_learned_aliases_unlocked()


def _persist_learned_aliases(cache: dict[str, str]) -> None:
    _ALIAS_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _ALIAS_CACHE_PATH.write_text(json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8")


def record_learned_alias(alias: str, drug_id: str) -> None:
    token = normalize_token(alias)
    did = normalize_token(drug_id)
    if not token or not did:
        return
    if len(token) < 4:
        return

    with _ALIAS_CACHE_LOCK:
        cache = _load_learned_aliases_unlocked()
        if cache.get(token) == did:
            return
        cache[token] = did
        try:
            _persist_learned_aliases(cache)
            global _LEARNED_ALIAS_CACHE
            _LEARNED_ALIAS_CACHE = cache
        except Exception:
            return


def all_alias_to_id() -> dict[str, str]:
    alias_map: dict[str, str] = {}
    for drug_id, record in MEDICATIONS.items():
        alias_map[record.canonical_name] = drug_id
        for alias in record.aliases:
            alias_map[alias] = drug_id
    alias_map.update(_load_learned_aliases())
    return alias_map


def normalize_token(value: str) -> str:
    base = unicodedata.normalize("NFKD", value.strip().lower()).encode("ascii", "ignore").decode("ascii")
    return " ".join(base.split())


def resolve_record_by_any_name(name: str) -> tuple[MedicationRecord | None, float, str | None, list[str]]:
    token = normalize_token(name)
    if not token:
        return None, 0.0, None, []

    alias_map = all_alias_to_id()
    if token in alias_map:
        drug_id = alias_map[token]
        confidence = 1.0 if token == drug_id else 0.94
        return MEDICATIONS[drug_id], confidence, token, []

    for drug_id, record in MEDICATIONS.items():
        if token in drug_id or drug_id in token:
            record_learned_alias(token, record.drug_id)
            return record, 0.72, record.canonical_name, []

    # Lightweight fuzzy matching for common misspellings/brand typos.
    close = get_close_matches(token, list(alias_map.keys()), n=3, cutoff=0.84)
    if close:
        top = close[0]
        top_drug = alias_map[top]
        ambiguities: list[str] = []
        for candidate in close[1:]:
            if alias_map[candidate] != top_drug:
                ambiguities.append(alias_map[candidate])

        if ambiguities:
            unique = sorted(list(dict.fromkeys([top_drug, *ambiguities])))
            return None, 0.0, None, unique

        record_learned_alias(token, top_drug)
        return MEDICATIONS[top_drug], 0.87, top, []

    return None, 0.0, None, []


def get_record_by_any_name(name: str) -> tuple[MedicationRecord | None, float, str | None]:
    record, confidence, matched, _ambiguities = resolve_record_by_any_name(name)
    return record, confidence, matched


def list_similar_medications(record: MedicationRecord) -> list[MedicationRecord]:
    similar: list[MedicationRecord] = []
    for candidate in MEDICATIONS.values():
        if candidate.drug_id == record.drug_id:
            continue

        same_class = candidate.pharmacologic_class == record.pharmacologic_class
        shared_ingredient = bool(set(candidate.ingredients) & set(record.ingredients))
        if same_class or shared_ingredient:
            similar.append(candidate)

    return similar
