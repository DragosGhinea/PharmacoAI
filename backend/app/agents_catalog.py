from __future__ import annotations

import json
import os
from pathlib import Path

from .agents_schemas import AgentDefinition, AgentProvider


def default_agent_definitions() -> list[AgentDefinition]:
    return [
        AgentDefinition(
            id="pharmacist-general-agent",
            name="Pharmacist General Assistant",
            description=(
                "Handles general pharmacist workflow questions and clarifies user intent when no medication-specific "
                "pipeline is required."
            ),
            provider=AgentProvider.GEMINI,
            model="gemini-3-flash-preview",
            system_prompt=(
                "You are a helpful pharmacist assistant having a conversation with a clinician. "
                "Your default behavior is to answer directly and conversationally using the conversation history "
                "and your own general pharmacy knowledge. "
                "Treat follow-up questions in an ongoing chat as continuations of the same discussion: "
                "answer them from prior turns and general knowledge, do NOT request a fresh medication lookup. "
                "Only treat a turn as a new medication-lookup request when the user explicitly names a specific "
                "medication as the new subject and asks for facts about it (indications, dose, interactions, contraindications, label info) "
                "that were not already covered in the conversation. "
                "Conceptual questions ('how do beta-blockers work?'), workflow questions, counseling questions, "
                "and follow-ups ('and for elderly patients?', 'why?', 'what about pregnancy?') are conversational — answer them yourself. "
                "Be concise, calm, and evidence-aware. When you are uncertain, say so rather than fabricating facts."
            ),
            api_key_env="GEMINI_API_KEY_1",
            style_tags=["basic-assistant"],
            risk_tier="informational",
            temperature=0.3,
        ),
        AgentDefinition(
            id="medication-normalization-agent",
            name="Medication Normalization Agent",
            description=(
                "Expands medication search terms by normalization and synonym/name-neighbor discovery only."
            ),
            provider=AgentProvider.GEMINI,
            model="gemini-3-flash-preview",
            system_prompt=(
                "You are the normalization stage. Use only provided tool evidence to build a precise search-term list. "
                "Do not provide final medical recommendations. "
                "Return a compact list of candidate search terms and why each is relevant."
            ),
            api_key_env="GEMINI_API_KEY_1",
            style_tags=["basic-assistant", "clinical-analyst"],
            risk_tier="informational",
            temperature=0.1,
        ),
        AgentDefinition(
            id="medication-evidence-gathering-agent",
            name="Medication Evidence Gathering Agent",
            description=(
                "Collects grounded medical evidence using normalized search terms and retrieval-only medication tools."
            ),
            provider=AgentProvider.GEMINI,
            model="gemini-3-flash-preview",
            system_prompt=(
                "You are the evidence gathering stage. Use only grounded retrieved outputs. "
                "Summarize facts, indications, and contraindications with source-aware uncertainty. "
                "Do not provide final patient-facing advice yet."
            ),
            api_key_env="GEMINI_API_KEY_2",
            style_tags=["basic-assistant", "clinical-analyst", "strategic-advisor"],
            risk_tier="informational",
            temperature=0.1,
        ),
        AgentDefinition(
            id="medication-answer-synthesis-agent",
            name="Medication Answer Synthesis Agent",
            description=(
                "Synthesizes gathered medical evidence into a direct answer aligned with the original user query."
            ),
            provider=AgentProvider.GEMINI,
            model="gemini-3-flash-preview",
            system_prompt=(
                "You are the synthesis stage. Reinforce and answer the original user intent using only gathered evidence. "
                "Highlight uncertainty and conflicting source findings when present."
            ),
            api_key_env="GEMINI_API_KEY_3",
            style_tags=["basic-assistant", "clinical-analyst", "strategic-advisor"],
            risk_tier="informational",
            temperature=0.2,
        ),
        AgentDefinition(
            id="medication-info-agent",
            name="Medication Info Agent",
            description=(
                "Retrieval-first medication intelligence agent: normalizes medication names, "
                "grounds answers in openFDA/DailyMed evidence, and produces clinician-facing summaries."
            ),
            provider=AgentProvider.GEMINI,
            model="gemini-3-flash-preview",
            system_prompt=(
                "You are a medication information agent. Use only provided evidence context and clearly label uncertainty. "
                "Do not fill missing information with general medical knowledge or assumptions. "
                "If required facts are not present in retrieved tool outputs, explicitly say the evidence is insufficient. "
                "Return structured, concise clinician-style output. "
                "If evidence is missing, state it and suggest likely English/INN normalization for non-English medication names before concluding. "
                "Always convert non-English medication terms to English/INN equivalents before running retrieval, "
                "and prefer English/INN query terms for every MCP search call. "
                "If a retrieval attempt returns source='dailymed', use the returned canonical name, aliases, and ingredients as synonym hints, "
                "then continue querying until a source='openfda' result is found or candidate synonyms are exhausted. "
                "MCP navigation policy: when an initial medication term fails, try close spelling/INN/salt variants; "
                "when normalization returns a canonical or synonym term, keep using that returned term in all subsequent steps; "
                "prefer iterative call->review->next-call behavior over repeating the same raw query."
            ),
            api_key_env="GEMINI_API_KEY_1",
            style_tags=["basic-assistant", "clinical-analyst"],
            risk_tier="informational",
            temperature=0.1,
        ),
        AgentDefinition(
            id="layman-translator-agent",
            name="Layman Translator Agent",
            description=(
                "Transforms clinical medication information into patient-friendly language while preserving safety warnings "
                "and citing grounded evidence."
            ),
            provider=AgentProvider.GEMINI,
            model="gemini-3-flash-preview",
            system_prompt=(
                "You are a patient-language translator. Rewrite technical medication content into clear, calm language "
                "without inventing medical facts. "
                "Do not introduce facts beyond retrieved evidence."
            ),
            api_key_env="GEMINI_API_KEY_3",
            style_tags=["basic-assistant"],
            risk_tier="informational",
            temperature=0.4,
        ),
        AgentDefinition(
            id="safety-contraindication-agent",
            name="Safety Contraindication Agent",
            description=(
                "Extracts contraindications, interactions, and do-not-combine risks from grounded label evidence, "
                "and returns escalation-oriented safety findings."
            ),
            provider=AgentProvider.GEMINI,
            model="gemini-3-flash-preview",
            system_prompt=(
                "You are a medication safety reviewer. Prioritize contraindications, interactions, and red flags. "
                "If context is missing, state it explicitly and avoid definitive diagnosis. "
                "Do not supplement with general knowledge when evidence is absent."
            ),
            api_key_env="GEMINI_API_KEY_2",
            style_tags=["clinical-analyst", "strategic-advisor"],
            risk_tier="clinical-risk",
            temperature=0.1,
        ),
    ]


def load_agent_definitions() -> list[AgentDefinition]:
    config_path = os.getenv("PHARMACOAI_AGENTS_CONFIG", "").strip()
    if not config_path:
        return default_agent_definitions()

    path = Path(config_path)
    if not path.exists() or not path.is_file():
        return default_agent_definitions()

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default_agent_definitions()

    if not isinstance(raw, list):
        return default_agent_definitions()

    parsed: list[AgentDefinition] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            parsed.append(AgentDefinition.model_validate(item))
        except Exception:
            continue

    return parsed or default_agent_definitions()
