"""Provider abstraction: the gateway talks to every LLM through this interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class ProviderResponse:
    content: str
    model: str
    finish_reason: str = "stop"
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


class ChatProvider(ABC):
    name: str = "base"

    @abstractmethod
    async def complete(
        self, messages: list[dict[str, Any]], model: str, params: dict[str, Any]
    ) -> ProviderResponse:
        """Send a chat completion request upstream."""

    async def close(self) -> None:  # pragma: no cover - optional hook
        return None
