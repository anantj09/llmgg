"""Rejects oversized inputs: protects cost and blunts context-stuffing attacks."""

from app.core.base_guard import BaseGuard
from app.core.context import RequestContext
from app.core.registry import register_guard
from app.core.types import Detection


@register_guard
class MaxLengthGuard(BaseGuard):
    name = "max_length"

    def configure(self, max_chars: int = 20_000) -> None:
        self.max_chars = max_chars

    async def scan(self, text: str, ctx: RequestContext) -> Detection:
        if len(text) <= self.max_chars:
            return Detection(triggered=False)
        return Detection(
            triggered=True,
            score=1.0,
            reason=f"Input is {len(text)} chars (limit {self.max_chars})",
            findings=[{"length": len(text), "limit": self.max_chars}],
        )
