"""OpenAI-compatible request schema. Unknown fields (temperature, top_p, ...)
are accepted and passed through to the upstream provider."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="allow")
    role: str
    content: str | list[dict[str, Any]] | None = None

    @field_validator("content")
    @classmethod
    def flatten_parts(cls, v):
        # Accept OpenAI "content parts" and keep only text, so every byte the
        # model sees has passed through the guards.
        if isinstance(v, list):
            return "\n".join(p.get("text", "") for p in v if p.get("type") == "text")
        return v


class ChatCompletionRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    model: str | None = None
    messages: list[ChatMessage] = Field(min_length=1)
    stream: bool = False

    def passthrough_params(self) -> dict[str, Any]:
        return dict(self.model_extra or {})
