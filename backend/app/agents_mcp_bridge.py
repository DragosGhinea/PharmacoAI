from __future__ import annotations

import json
from typing import Any

from backend.mcp import server as mcp_server


def _serialize(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=True)
    except Exception:
        return str(value)


def call_mcp_tool(tool_name: str, *, args: dict[str, Any], caller_id: str) -> dict[str, Any]:
    tool_map = {
        "normalize_medication_name": mcp_server.normalize_medication_name,
        "search_medication_facts": mcp_server.search_medication_facts,
        "search_medication_indications": mcp_server.search_medication_indications,
        "search_medication_contraindications": mcp_server.search_medication_contraindications,
        "find_similar_medications": mcp_server.find_similar_medications,
        "find_synonym_or_name_neighbors": mcp_server.find_synonym_or_name_neighbors,
        "collect_missing_context": mcp_server.collect_missing_context,
        "check_contraindications": mcp_server.check_contraindications,
        "check_interactions": mcp_server.check_interactions,
        "explain_for_patient": mcp_server.explain_for_patient,
    }

    if tool_name not in tool_map:
        return {
            "tool_name": tool_name,
            "status": "error",
            "transport": "in-process",
            "input": args,
            "output": None,
            "error": "Unknown MCP tool",
            "output_summary": "Unknown MCP tool",
        }

    fn = tool_map[tool_name]
    try:
        payload = dict(args)
        payload["caller_id"] = caller_id
        output = fn(**payload)
        status = "success"
        if isinstance(output, dict) and output.get("ok") is False:
            status = "warning"
        return {
            "tool_name": tool_name,
            "status": status,
            "transport": "in-process",
            "input": args,
            "output": output,
            "error": None,
            "output_summary": _serialize(output),
        }
    except Exception as exc:  # pragma: no cover - defensive fallback for runtime issues
        return {
            "tool_name": tool_name,
            "status": "error",
            "transport": "in-process",
            "input": args,
            "output": None,
            "error": str(exc),
            "output_summary": str(exc),
        }
