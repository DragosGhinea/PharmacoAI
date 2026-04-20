from __future__ import annotations

import json
import os
import unicodedata
from typing import Any

from mcp.server.fastmcp import FastMCP

from ..env_loader import load_root_env

load_root_env()

from .audit import log_audit, setup_audit_logger
from .data import normalize_token
from .external_data import fetch_openfda_facts, fetch_openfda_related_medications
from .rate_limit import build_default_limiter
from .safety import collect_context_gaps, warning_from_context_gaps
from .schemas import MCPError, MCPWarning, ToolEnvelope

setup_audit_logger()
RATE_LIMITER = build_default_limiter()
USE_EXTERNAL_DATA = os.getenv("MCP_ENABLE_OPENFDA", "1") in {"1", "true", "TRUE", "yes", "YES"}
MCP_HOST = os.getenv("MCP_HOST", "127.0.0.1")
MCP_PORT = int(os.getenv("MCP_PORT", "8010"))
mcp = FastMCP(
    "PharmacoAI Medication MCP",
    host=MCP_HOST,
    port=MCP_PORT,
    streamable_http_path="/mcp",
    stateless_http=True,
    json_response=True,
)


def _name_candidates(name: str) -> list[str]:
    base = normalize_token(name)
    if not base:
        return []
    ascii_base = unicodedata.normalize("NFKD", base).encode("ascii", "ignore").decode("ascii")
    variants = [
        base,
        ascii_base,
        base.replace(" sodic", " sodium").replace(" de sodiu", " sodium"),
        ascii_base.replace(" sodic", " sodium").replace(" de sodiu", " sodium"),
        base.replace(" sodic", "").replace(" de sodiu", "").strip(),
    ]
    deduped: list[str] = []
    for item in variants:
        token = normalize_token(item)
        if token and token not in deduped:
            deduped.append(token)
    return deduped


def _resolve_by_name(name: str) -> tuple[dict[str, Any] | None, float, str | None, list[str]]:
    if not USE_EXTERNAL_DATA:
        return None, 0.0, None, []

    for candidate in _name_candidates(name):
        external = fetch_openfda_facts(candidate)
        if external is not None:
            return external, 0.88, candidate, []

    return None, 0.0, None, []


def _resolve_by_id(drug_id: str) -> dict[str, Any] | None:
    by_name, _, _, _ = _resolve_by_name(drug_id.replace("-", " "))
    if by_name is not None:
        return by_name

    if not USE_EXTERNAL_DATA:
        return None

    return fetch_openfda_facts(drug_id)


def _envelope(
    *,
    ok: bool,
    risk_tier: str,
    warnings: list[dict[str, Any]] | None = None,
    data: dict[str, Any] | None = None,
    error: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return ToolEnvelope(
        ok=ok,
        risk_tier=risk_tier,
        warnings=[MCPWarning(**item) for item in (warnings or [])],
        data=data or {},
        error=MCPError(**error) if error else None,
    ).model_dump(mode="json")


def _preflight(capability: str, caller_id: str, risk_tier: str) -> dict[str, Any] | None:
    key = f"{caller_id}:{capability}"
    allowed, retry_after = RATE_LIMITER.allow(key)
    if allowed:
        return None

    log_audit(
        capability=capability,
        caller_id=caller_id,
        status="error",
        risk_tier=risk_tier,
        metadata={"reason": "rate_limited", "retry_after_seconds": retry_after},
    )
    return _envelope(
        ok=False,
        risk_tier=risk_tier,
        error={
            "code": "RATE_LIMITED",
            "message": "Too many requests for this capability.",
            "retry_after_seconds": retry_after,
        },
    )


@mcp.tool(
    title="Normalize Medication Name",
    description="Map user-provided medication text to a canonical concept with confidence and evidence.",
)
def normalize_medication_name(name: str, caller_id: str = "anonymous") -> dict[str, Any]:
    """Normalize free text medication names to canonical medication concepts."""
    blocked = _preflight("normalize_medication_name", caller_id, "informational")
    if blocked:
        return blocked

    payload, confidence, matched_on, ambiguities = _resolve_by_name(name)
    if payload is None:
        if ambiguities:
            result = _envelope(
                ok=False,
                risk_tier="informational",
                error={
                    "code": "NEEDS_CLARIFICATION",
                    "message": "Medication name is ambiguous. Please choose one of the suggested options.",
                },
                data={"suggestions": ambiguities[:5]},
            )
            log_audit("normalize_medication_name", caller_id, "warn", "informational")
            return result
        result = _envelope(
            ok=False,
            risk_tier="informational",
            error={
                "code": "NOT_FOUND",
                "message": "Medication name could not be normalized.",
            },
        )
        log_audit("normalize_medication_name", caller_id, "error", "informational")
        return result

    data = {
        "drug_id": payload["drug_id"],
        "canonical_name": payload["canonical_name"],
        "matched_on": matched_on,
        "aliases": payload.get("aliases", []),
        "confidence": confidence,
        "source": payload.get("source", "openfda"),
        "evidence": [
            {
                "uri": f"drug://label/{payload['drug_id']}",
                "snippets": [
                    f"Matched input to canonical concept '{payload['canonical_name']}'.",
                ],
            }
        ],
    }
    result = _envelope(ok=True, risk_tier="informational", data=data)
    log_audit("normalize_medication_name", caller_id, "success", "informational")
    return result


@mcp.tool(
    title="Search Medication Facts",
    description="Retrieve core medication facts including ingredients, indications, dosage form, and class.",
)
def search_medication_facts(name: str, caller_id: str = "anonymous") -> dict[str, Any]:
    """Fetch ingredients, indications, dosage form, and class for a medication."""
    blocked = _preflight("search_medication_facts", caller_id, "informational")
    if blocked:
        return blocked

    payload, _, _, ambiguities = _resolve_by_name(name)
    if payload is None:
        if ambiguities:
            result = _envelope(
                ok=False,
                risk_tier="informational",
                error={
                    "code": "NEEDS_CLARIFICATION",
                    "message": "Medication name is ambiguous. Please clarify before retrieving facts.",
                },
                data={"suggestions": ambiguities[:5]},
            )
            log_audit("search_medication_facts", caller_id, "warn", "informational")
            return result
        result = _envelope(
            ok=False,
            risk_tier="informational",
            error={"code": "NOT_FOUND", "message": "Medication facts were not found."},
        )
        log_audit("search_medication_facts", caller_id, "error", "informational")
        return result

    data = {
        "drug_id": payload["drug_id"],
        "canonical_name": payload["canonical_name"],
        "ingredients": payload.get("ingredients", []),
        "indications": payload.get("indications", []),
        "dosage_form": payload.get("dosage_form", "unknown"),
        "pharmacologic_class": payload.get("pharmacologic_class", "unknown"),
        "source": payload.get("source", "openfda"),
        "evidence": [
            {
                "uri": f"drug://label/{payload['drug_id']}",
                "snippets": payload.get("evidence", {}).get("label", []),
            }
        ],
    }

    result = _envelope(ok=True, risk_tier="informational", data=data)
    log_audit("search_medication_facts", caller_id, "success", "informational")
    return result


@mcp.tool(
    title="Find Similar Medications",
    description="Return alternatives related by ingredient or class using local and external evidence sources.",
)
def find_similar_medications(name: str, caller_id: str = "anonymous") -> dict[str, Any]:
    """Return alternatives related by class or active ingredient."""
    blocked = _preflight("find_similar_medications", caller_id, "informational")
    if blocked:
        return blocked

    payload, _, _, _ = _resolve_by_name(name)
    if payload is None:
        result = _envelope(
            ok=False,
            risk_tier="informational",
            error={
                "code": "NOT_FOUND",
                "message": "No source medication found in external sources.",
            },
        )
        log_audit("find_similar_medications", caller_id, "error", "informational")
        return result

    target_name = str(payload.get("canonical_name") or name).strip()
    external_alternatives: list[dict[str, Any]] = []
    if USE_EXTERNAL_DATA:
        external_alternatives = fetch_openfda_related_medications(target_name, limit=5)

    data = {
        "drug_id": payload["drug_id"],
        "canonical_name": payload["canonical_name"],
        "alternatives": external_alternatives,
        "evidence": [
            {
                "uri": f"drug://classes/{payload['drug_id']}",
                "snippets": [
                    "Alternatives are retrieved from external source neighborhood search.",
                ],
            }
        ],
        "source": "openfda",
    }

    result = _envelope(ok=True, risk_tier="informational", data=data)
    log_audit("find_similar_medications", caller_id, "success", "informational")
    return result


@mcp.tool(
    title="Collect Missing Context",
    description="Detect missing patient context required for safety checks and return completeness warnings.",
)
def collect_missing_context(patient_context: dict[str, Any], caller_id: str = "anonymous") -> dict[str, Any]:
    """Detect missing context fields required for credible safety analysis."""
    blocked = _preflight("collect_missing_context", caller_id, "informational")
    if blocked:
        return blocked

    gaps = collect_context_gaps(patient_context)
    warnings: list[dict[str, Any]] = []
    if gaps["required_missing"]:
        warnings = warning_from_context_gaps(patient_context, "collect_missing_context")

    data = {
        "required_missing": gaps["required_missing"],
        "recommended_missing": gaps["recommended_missing"],
        "completeness": gaps["completeness"],
    }
    status = "warn" if warnings else "success"
    result = _envelope(ok=True, risk_tier="informational", warnings=warnings, data=data)
    log_audit("collect_missing_context", caller_id, status, "informational")
    return result


@mcp.tool(
    title="Check Contraindications",
    description="Evaluate contraindications and high-risk conditions using provided patient context.",
)
def check_contraindications(
    medication_name: str,
    patient_context: dict[str, Any],
    caller_id: str = "anonymous",
) -> dict[str, Any]:
    """Check contraindications and high-risk populations for a medication."""
    blocked = _preflight("check_contraindications", caller_id, "clinical-risk")
    if blocked:
        return blocked

    payload, _, _, _ = _resolve_by_name(medication_name)
    if payload is None:
        result = _envelope(
            ok=False,
            risk_tier="clinical-risk",
            error={"code": "NOT_FOUND", "message": "Medication not found for contraindication check."},
        )
        log_audit("check_contraindications", caller_id, "error", "clinical-risk")
        return result

    warnings = warning_from_context_gaps(patient_context, "check_contraindications")

    red_flags: list[str] = []
    pregnancy_flag = str(patient_context.get("pregnancy_or_breastfeeding", "")).lower()
    if "pregnan" in pregnancy_flag and payload["drug_id"] in {"warfarin", "ibuprofen"}:
        red_flags.append("Pregnancy status indicates elevated risk for this medication.")

    allergies = [item.lower() for item in patient_context.get("allergies", [])]
    if payload["drug_id"] == "amoxicillin" and any("penicillin" in item for item in allergies):
        red_flags.append("Penicillin allergy reported; beta-lactam hypersensitivity risk is high.")

    data = {
        "drug_id": payload["drug_id"],
        "canonical_name": payload["canonical_name"],
        "contraindications": payload.get("contraindications", []),
        "red_flags": red_flags,
        "source": payload.get("source", "openfda"),
        "evidence": [
            {
                "uri": f"drug://contraindications/{payload['drug_id']}",
                "snippets": payload.get("evidence", {}).get("contraindications", []),
            }
        ],
    }

    status = "warn" if warnings or red_flags else "success"
    result = _envelope(ok=True, risk_tier="clinical-risk", warnings=warnings, data=data)
    log_audit(
        "check_contraindications",
        caller_id,
        status,
        "clinical-risk",
        metadata={"red_flag_count": len(red_flags)},
    )
    return result


@mcp.tool(
    title="Check Interactions",
    description="Analyze drug-drug interaction risk for a target medication against a medication list.",
)
def check_interactions(
    medication_name: str,
    current_medications: list[str],
    patient_context: dict[str, Any] | None = None,
    caller_id: str = "anonymous",
) -> dict[str, Any]:
    """Check drug-drug interactions and provide evidence-backed risk output."""
    blocked = _preflight("check_interactions", caller_id, "clinical-risk")
    if blocked:
        return blocked

    payload, _, _, _ = _resolve_by_name(medication_name)
    if payload is None:
        result = _envelope(
            ok=False,
            risk_tier="clinical-risk",
            error={"code": "NOT_FOUND", "message": "Medication not found for interaction check."},
        )
        log_audit("check_interactions", caller_id, "error", "clinical-risk")
        return result

    context = patient_context or {}
    if "current_medications" not in context:
        context = {**context, "current_medications": current_medications}
    warnings = warning_from_context_gaps(context, "check_interactions")

    findings: list[dict[str, str]] = []
    interactions = payload.get("interactions", {})
    if isinstance(interactions, dict):
        for med in current_medications:
            lookup_token = normalize_token(med)
            interaction = interactions.get(lookup_token)
            if interaction:
                findings.append(
                    {
                        "with": lookup_token,
                        "severity": interaction["severity"],
                        "message": interaction["message"],
                    }
                )
    else:
        interaction_text = " ".join(interactions) if isinstance(interactions, list) else ""
        low = interaction_text.lower()
        for med in current_medications:
            token = med.strip().lower()
            if token and token in low:
                findings.append(
                    {
                        "with": token,
                        "severity": "moderate",
                        "message": "Mentioned in retrieved interaction section; review clinically.",
                    }
                )

    data = {
        "drug_id": payload["drug_id"],
        "canonical_name": payload["canonical_name"],
        "checked_against": current_medications,
        "findings": findings,
        "source": payload.get("source", "openfda"),
        "evidence": [
            {
                "uri": f"drug://interactions/{payload['drug_id']}",
                "snippets": payload.get("evidence", {}).get("interactions", []),
            }
        ],
    }

    status = "warn" if warnings else "success"
    result = _envelope(ok=True, risk_tier="clinical-risk", warnings=warnings, data=data)
    log_audit(
        "check_interactions",
        caller_id,
        status,
        "clinical-risk",
        metadata={"finding_count": len(findings)},
    )
    return result


@mcp.tool(
    title="Explain For Patient",
    description="Rewrite grounded evidence in plain-language patient-safe format with citation context.",
)
def explain_for_patient(
    medication_name: str,
    evidence_snippets: list[str] | None = None,
    caller_id: str = "anonymous",
) -> dict[str, Any]:
    """Rewrite grounded medication evidence in plain language for patient communication."""
    blocked = _preflight("explain_for_patient", caller_id, "informational")
    if blocked:
        return blocked

    payload, _, _, _ = _resolve_by_name(medication_name)
    if payload is None:
        result = _envelope(
            ok=False,
            risk_tier="informational",
            error={"code": "NOT_FOUND", "message": "Medication not found for patient explanation."},
        )
        log_audit("explain_for_patient", caller_id, "error", "informational")
        return result

    snippets = evidence_snippets or payload.get("evidence", {}).get("label", [])
    simplified = " ".join(
        [
            f"Key point: {snippet}" if not snippet.lower().startswith("key point") else snippet
            for snippet in snippets
        ]
    )

    data = {
        "drug_id": payload["drug_id"],
        "canonical_name": payload["canonical_name"],
        "plain_language_explanation": (
            f"{payload['canonical_name'].title()} may help for {', '.join(payload.get('indications', []))}. "
            f"{simplified} This explanation is educational and not a diagnosis."
        ),
        "source": payload.get("source", "openfda"),
        "evidence": [
            {
                "uri": f"drug://patient-leaflet/{payload['drug_id']}",
                "snippets": snippets,
            }
        ],
        "disclaimer": "Educational information only. Consult a licensed clinician for medical decisions.",
    }

    result = _envelope(ok=True, risk_tier="informational", data=data)
    log_audit("explain_for_patient", caller_id, "success", "informational")
    return result


@mcp.resource(
    "drug://label/{drug_id}",
    title="Drug Label Resource",
    description="Read a normalized drug label summary with indications and dosage form.",
)
def resource_label(drug_id: str) -> str:
    payload = _resolve_by_id(drug_id)
    if payload is None:
        return json.dumps({"error": "Resource not found"})

    payload = {
        "drug_id": payload["drug_id"],
        "canonical_name": payload["canonical_name"],
        "indications": payload.get("indications", []),
        "dosage_form": payload.get("dosage_form", "unknown"),
        "label_summary": payload.get("evidence", {}).get("label", []),
        "source": payload.get("source", "openfda"),
    }
    return json.dumps(payload)


@mcp.resource(
    "drug://ingredients/{drug_id}",
    title="Drug Ingredients Resource",
    description="Read active ingredient data for a medication concept.",
)
def resource_ingredients(drug_id: str) -> str:
    payload = _resolve_by_id(drug_id)
    if payload is None:
        return json.dumps({"error": "Resource not found"})
    return json.dumps({"drug_id": payload["drug_id"], "ingredients": payload.get("ingredients", [])})


@mcp.resource(
    "drug://classes/{drug_id}",
    title="Drug Class Resource",
    description="Read class mapping metadata for a medication concept.",
)
def resource_classes(drug_id: str) -> str:
    payload = _resolve_by_id(drug_id)
    if payload is None:
        return json.dumps({"error": "Resource not found"})
    return json.dumps({"drug_id": payload["drug_id"], "class": payload.get("pharmacologic_class", "unknown")})


@mcp.resource(
    "drug://contraindications/{drug_id}",
    title="Contraindications Resource",
    description="Read contraindication snippets and evidence for a medication concept.",
)
def resource_contraindications(drug_id: str) -> str:
    payload = _resolve_by_id(drug_id)
    if payload is None:
        return json.dumps({"error": "Resource not found"})
    return json.dumps(
        {
            "drug_id": payload["drug_id"],
            "contraindications": payload.get("contraindications", []),
            "evidence": payload.get("evidence", {}).get("contraindications", []),
        }
    )


@mcp.resource(
    "drug://interactions/{drug_id}",
    title="Interactions Resource",
    description="Read interaction section content and evidence for a medication concept.",
)
def resource_interactions(drug_id: str) -> str:
    payload = _resolve_by_id(drug_id)
    if payload is None:
        return json.dumps({"error": "Resource not found"})
    return json.dumps(
        {
            "drug_id": payload["drug_id"],
            "interactions": payload.get("interactions", []),
            "evidence": payload.get("evidence", {}).get("interactions", []),
        }
    )


@mcp.resource(
    "drug://patient-leaflet/{drug_id}",
    title="Patient Leaflet Resource",
    description="Read patient-facing leaflet text for a medication concept.",
)
def resource_leaflet(drug_id: str) -> str:
    payload = _resolve_by_id(drug_id)
    if payload is None:
        return json.dumps({"error": "Resource not found"})
    return json.dumps({"drug_id": payload["drug_id"], "leaflet": payload.get("patient_leaflet", "")})


@mcp.resource(
    "drug://evidence/{drug_id}/{section}",
    title="Evidence Snippets Resource",
    description="Read evidence snippets for a specific medication and section key.",
)
def resource_evidence(drug_id: str, section: str) -> str:
    payload = _resolve_by_id(drug_id)
    if payload is None:
        return json.dumps({"error": "Resource not found"})
    snippets = payload.get("evidence", {}).get(section, [])
    return json.dumps({"drug_id": payload["drug_id"], "section": section, "snippets": snippets})


@mcp.prompt(
    title="Medication Summary Prompt",
    description="Template for concise clinician-facing medication summary generation.",
)
def medication_summary(medication_name: str) -> str:
    return (
        "Generate a concise clinical summary with: active ingredient, primary indications, "
        "key contraindications, and interaction highlights. Use only grounded evidence snippets "
        "from the provided MCP resources."
    )


@mcp.prompt(
    title="Patient Explanation Prompt",
    description="Template for patient-readable explanation of medication usage and risks.",
)
def patient_explanation(medication_name: str, reading_level: str = "plain") -> str:
    return (
        f"Explain {medication_name} in {reading_level} language. Include what it is for, "
        "how to use safely, and red flags that require urgent care. Do not invent facts."
    )


@mcp.prompt(
    title="Interaction Review Prompt",
    description="Template for reviewing interaction risk between a medication and a med list.",
)
def interaction_review(target_medication: str, med_list: str) -> str:
    return (
        f"Review interaction risks for {target_medication} against this list: {med_list}. "
        "Return severity-ranked findings with evidence citations and missing-context warnings."
    )


@mcp.prompt(
    title="Contraindication Review Prompt",
    description="Template for contraindication review against patient condition context.",
)
def contraindication_review(target_medication: str, conditions_summary: str) -> str:
    return (
        f"Review contraindications for {target_medication} given: {conditions_summary}. "
        "Highlight high-risk populations, red flags, and escalation recommendations."
    )


@mcp.prompt(
    title="Compare Medications Prompt",
    description="Template for comparative analysis between two medication options.",
)
def compare_medications(option_a: str, option_b: str) -> str:
    return (
        f"Compare {option_a} versus {option_b} by ingredients, use cases, major risks, "
        "and interaction profile. Stay grounded in MCP evidence resources only."
    )


@mcp.prompt(
    title="Red Flag Review Prompt",
    description="Template for surfacing escalation red flags from patient snapshots.",
)
def red_flag_review(target_medication: str, patient_snapshot: str) -> str:
    return (
        f"For {target_medication}, identify red flags from this snapshot: {patient_snapshot}. "
        "If context is incomplete, explicitly list missing critical fields before conclusions."
    )


def main() -> None:
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
