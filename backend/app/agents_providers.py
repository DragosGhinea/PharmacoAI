from __future__ import annotations

import os
from typing import Protocol

import httpx
from fastapi import HTTPException, status

from .agents_schemas import AgentDefinition, AgentProvider


def _provider_timeout_seconds() -> float:
    raw = os.getenv("PHARMACOAI_AGENT_PROVIDER_TIMEOUT_SECONDS", "90").strip()
    try:
        value = float(raw)
    except ValueError:
        return 90.0
    return max(5.0, value)


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

        async with httpx.AsyncClient(timeout=_provider_timeout_seconds()) as client:
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
    @staticmethod
    def _build_model_candidates(model: str) -> list[str]:
        raw_fallbacks = os.getenv(
            "PHARMACOAI_GEMINI_MODEL_FALLBACKS",
            "gemini-3-flash-preview,gemini-2.0-flash,gemini-1.5-flash-latest,gemini-1.5-pro-latest",
        )
        configured_fallbacks = [item.strip() for item in raw_fallbacks.split(",") if item.strip()]
        candidates = [model, *configured_fallbacks]
        unique: list[str] = []
        for candidate in candidates:
            if candidate not in unique:
                unique.append(candidate)
        return unique

    @staticmethod
    def _extract_error_detail(response: httpx.Response) -> str:
        try:
            payload = response.json()
        except Exception:
            return response.text.strip()[:500]

        if isinstance(payload, dict):
            error_obj = payload.get("error")
            if isinstance(error_obj, dict):
                message = error_obj.get("message")
                if isinstance(message, str) and message.strip():
                    return message.strip()
            message = payload.get("message")
            if isinstance(message, str) and message.strip():
                return message.strip()

        return str(payload)[:500]

    async def generate(self, agent: AgentDefinition, messages: list[dict[str, str]]) -> str:
        api_key = os.getenv(agent.api_key_env, "").strip()
        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Missing Gemini API key for env var '{agent.api_key_env}'",
            )

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

        attempts: list[tuple[str, int, str]] = []
        data: dict[str, object] | None = None
        for model_name in self._build_model_candidates(agent.model):
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
            async with httpx.AsyncClient(timeout=_provider_timeout_seconds()) as client:
                response = await client.post(url, json=payload)

            if response.status_code >= 400:
                error_detail = self._extract_error_detail(response)
                attempts.append((model_name, response.status_code, error_detail))
                if response.status_code in {404, 429, 500, 502, 503, 504}:
                    continue

                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=(
                        f"Gemini request failed for '{agent.id}' model '{model_name}' "
                        f"({response.status_code}): {error_detail}"
                    ),
                )

            parsed = response.json()
            if isinstance(parsed, dict):
                data = parsed
                break

            attempts.append((model_name, response.status_code, "Unexpected non-object Gemini response payload"))

        if data is None:
            attempted_models = ", ".join([item[0] for item in attempts]) or agent.model
            last_detail = attempts[-1][2] if attempts else "Unknown Gemini error"
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=(
                    f"Gemini request failed for '{agent.id}'. Tried models: {attempted_models}. "
                    f"Last error: {last_detail}"
                ),
            )

        candidates = data.get("candidates", [])
        if isinstance(candidates, list) and candidates:
            for candidate in candidates:
                if not isinstance(candidate, dict):
                    continue
                content = candidate.get("content")
                if not isinstance(content, dict):
                    continue
                parts = content.get("parts", [])
                if not isinstance(parts, list):
                    continue
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
