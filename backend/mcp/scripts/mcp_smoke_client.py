from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


def _to_plain(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return value


async def run_smoke(server_url: str) -> None:
    async with streamable_http_client(server_url) as (read_stream, write_stream, _get_session_id):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            tools = await session.list_tools()
            resources = await session.list_resources()
            resource_templates = await session.list_resource_templates()
            prompts = await session.list_prompts()

            print("== MCP capability discovery ==")
            print("tools:", [item.name for item in tools.tools])
            print("resources:", [item.uri for item in resources.resources])
            print("resource_templates:", [item.uriTemplate for item in resource_templates.resourceTemplates])
            print("prompts:", [item.name for item in prompts.prompts])

            print("\n== Tool call: search_medication_facts ==")
            tool_result = await session.call_tool(
                "search_medication_facts",
                {"name": "ibuprofen", "caller_id": "smoke-client"},
            )
            print(json.dumps(_to_plain(tool_result), indent=2))

            print("\n== Resource read: drug://label/ibuprofen ==")
            resource_result = await session.read_resource("drug://label/ibuprofen")
            print(json.dumps(_to_plain(resource_result), indent=2))

            print("\n== Prompt fetch: interaction_review ==")
            prompt_result = await session.get_prompt(
                "interaction_review",
                {
                    "target_medication": "ibuprofen",
                    "med_list": "warfarin, omeprazole",
                },
            )
            print(json.dumps(_to_plain(prompt_result), indent=2))


def main() -> None:
    server_url = os.getenv("MCP_SERVER_URL", "http://127.0.0.1:8010/mcp")
    asyncio.run(run_smoke(server_url))


if __name__ == "__main__":
    main()
