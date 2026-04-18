from __future__ import annotations

from dataclasses import dataclass


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
}


def all_alias_to_id() -> dict[str, str]:
    alias_map: dict[str, str] = {}
    for drug_id, record in MEDICATIONS.items():
        alias_map[record.canonical_name] = drug_id
        for alias in record.aliases:
            alias_map[alias] = drug_id
    return alias_map


def normalize_token(value: str) -> str:
    return " ".join(value.strip().lower().split())


def get_record_by_any_name(name: str) -> tuple[MedicationRecord | None, float, str | None]:
    token = normalize_token(name)
    if not token:
        return None, 0.0, None

    alias_map = all_alias_to_id()
    if token in alias_map:
        drug_id = alias_map[token]
        confidence = 1.0 if token == drug_id else 0.94
        return MEDICATIONS[drug_id], confidence, token

    for drug_id, record in MEDICATIONS.items():
        if token in drug_id or drug_id in token:
            return record, 0.72, record.canonical_name

    return None, 0.0, None


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
