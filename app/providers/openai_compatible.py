"""Any OpenAI-compatible endpoint: OpenAI, Groq, Together, OpenRouter, Ollama, vLLM."""

from __future__ import annotations

from typing import Any

import httpx

from app.core.errors import UpstreamError
from app.providers.base import ChatProvider, ProviderResponse


class OpenAICompatibleProvider(ChatProvider):
    name = "openai_compatible"

    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout_s: float = 60.0,
        transport: httpx.AsyncBaseTransport | None = None,  # injectable for tests
    ) -> None:
        if not api_key:
            raise ValueError("UPSTREAM_API_KEY is required for the openai_compatible provider")
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout_s,
            transport=transport,
        )

    async def complete(
        self, messages: list[dict[str, Any]], model: str, params: dict[str, Any]
    ) -> ProviderResponse:
        payload = {**params, "model": model, "messages": messages, "stream": False}
        try:
            resp = await self._client.post("/chat/completions", json=payload)
        except httpx.HTTPError as exc:
            raise UpstreamError(f"Upstream request failed: {exc!r}") from exc
        if resp.status_code >= 400:
            raise UpstreamError(f"Upstream returned {resp.status_code}: {resp.text[:300]}")

        data = resp.json()
        try:
            choice = data["choices"][0]
            usage = data.get("usage") or {}
            return ProviderResponse(
                content=choice["message"].get("content") or "",
                model=data.get("model", model),
                finish_reason=choice.get("finish_reason") or "stop",
                prompt_tokens=usage.get("prompt_tokens"),
                completion_tokens=usage.get("completion_tokens"),
            )
        except (KeyError, IndexError, TypeError) as exc:
            raise UpstreamError(f"Unexpected upstream response shape: {data!r:.300}") from exc

    async def close(self) -> None:
        await self._client.aclose()
