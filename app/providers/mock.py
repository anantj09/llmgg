"""Deterministic offline provider. Echoes what it received, which makes it easy
to *see* that the LLM only ever got redacted text. Saying "simulate leak"
makes it return a fake credential so you can demo the output guards."""

from __future__ import annotations

import asyncio
from typing import Any

from app.providers.base import ChatProvider, ProviderResponse

# AWS's own documentation example key, not a real credential.
FAKE_LEAK = "Sure! The deploy key is AKIAIOSFODNN7EXAMPLE and the admin email is ops@internal-corp.com."


class MockProvider(ChatProvider):
    name = "mock"

    def __init__(self, latency_ms: int = 40) -> None:
        self.latency_s = latency_ms / 1000

    async def complete(
        self, messages: list[dict[str, Any]], model: str, params: dict[str, Any]
    ) -> ProviderResponse:
        await asyncio.sleep(self.latency_s)
        last_user = next(
            (m.get("content") or "" for m in reversed(messages) if m.get("role") == "user"), ""
        )
        if "simulate leak" in last_user.lower():
            content = FAKE_LEAK
        else:
            content = f"[mock model] I received: {last_user[:500]}"
        prompt_chars = sum(len(m.get("content") or "") for m in messages)
        return ProviderResponse(
            content=content,
            model=f"mock/{model}",
            prompt_tokens=max(1, prompt_chars // 4),
            completion_tokens=max(1, len(content) // 4),
        )
