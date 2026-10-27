"""Per-request state shared across guards (e.g. the reversible PII vault)."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.core.types import Stage


@dataclass
class RequestContext:
    request_id: str
    stage: Stage = Stage.INPUT
    # placeholder -> original value. Only populated during the INPUT stage, so
    # the upstream LLM never sees raw PII but the caller can get it back.
    vault: dict[str, str] = field(default_factory=dict)
    _reverse: dict[str, str] = field(default_factory=dict)
    _counters: dict[str, int] = field(default_factory=dict)

    def placeholder_for(self, entity: str, value: str) -> str:
        """Return a stable placeholder such as <EMAIL_1> for a sensitive value."""
        if value in self._reverse:
            return self._reverse[value]
        self._counters[entity] = self._counters.get(entity, 0) + 1
        placeholder = f"<{entity}_{self._counters[entity]}>"
        self.vault[placeholder] = value
        self._reverse[value] = placeholder
        return placeholder

    def restore(self, text: str) -> str:
        """Swap placeholders back to their original values."""
        for placeholder, original in self.vault.items():
            text = text.replace(placeholder, original)
        return text
