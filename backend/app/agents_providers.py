from __future__ import annotations

import os
from typing import Protocol

import httpx
from fastapi import HTTPException, status

from .agents_schemas import AgentDefinition, AgentProvider


class AgentProviderClient(Protocol):
    async def generate(self, agent: AgentDefinition, messages: list[dict[str, str]]) -> str: ...


class GenericApiAgentClient:
    async def generate(self, agent: AgentDefinition, messages: list[dict[str, str]]) -> str:
        api_key = os.getenv(agent.api_key_env, "").strip()
        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Missing API key for agent '{agent.id}' in env var '{agent.api_key_env}'",
            )

        if not agent.base_url:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Agent '{agent.id}' is missing base_url for API provider",
            )

        payload = {
            "model": agent.model,
            "messages": messages,
            "temperature": agent.temperature,
        }

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(agent.base_url, json=payload, headers=headers)

        if response.status_code >= 400:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Agent provider request failed for '{agent.id}' ({response.status_code})",
            )

        data = response.json()
        choices = data.get("choices", [])
        if isinstance(choices, list) and choices:
            message = choices[0].get("message", {})
            content = message.get("content")
            if isinstance(content, str) and content.strip():
                return content.strip()

        text = data.get("output") or data.get("response")
        if isinstance(text, str) and text.strip():
            return text.strip()

        return "No content returned by API agent provider."


class GeminiAgentClient:
    async def generate(self, agent: AgentDefinition, messages: list[dict[str, str]]) -> str:
        api_key = os.getenv(agent.api_key_env, "").strip()
        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Missing Gemini API key for env var '{agent.api_key_env}'",
            )

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{agent.model}:generateContent?key={api_key}"

        contents = []
        for msg in messages:
            role = "user" if msg["role"] in {"user", "system"} else "model"
            contents.append({"role": role, "parts": [{"text": msg["content"]}]})

        payload = {
            "systemInstruction": {
                "role": "user",
                "parts": [{"text": agent.system_prompt}],
            },
            "contents": contents,
            "generationConfig": {
                "temperature": agent.temperature,
            },
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload)

        if response.status_code >= 400:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Gemini request failed for '{agent.id}' ({response.status_code})",
            )

        data = response.json()
        candidates = data.get("candidates", [])
        if isinstance(candidates, list) and candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            if isinstance(parts, list):
                text = "\n".join(
                    [str(part.get("text", "")) for part in parts if isinstance(part, dict)]
                ).strip()
                if text:
                    return text

        return "No content returned by Gemini provider."


def get_provider_client(provider: AgentProvider) -> AgentProviderClient:
    if provider == AgentProvider.GEMINI:
        return GeminiAgentClient()
    return GenericApiAgentClient()
