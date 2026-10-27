"""Business-rule guard: flag or block configured topics (e.g. competitors,
medical or legal advice) using whole-word phrase matching."""

from __future__ import annotations

import re

from app.core.base_guard import BaseGuard
from app.core.context import RequestContext
from app.core.registry import register_guard
from app.core.types import Detection
from app.guards._text import normalize


@register_guard
class KeywordPolicyGuard(BaseGuard):
    name = "keyword_policy"

    def configure(self, categories: dict[str, list[str]] | None = None) -> None:
        self.patterns: dict[str, re.Pattern[str]] = {}
        for category, phrases in (categories or {}).items():
            cleaned = [re.escape(normalize(p)) for p in phrases if p.strip()]
            if cleaned:
                self.patterns[category] = re.compile(r"\b(?:" + "|".join(cleaned) + r")\b")

    async def scan(self, text: str, ctx: RequestContext) -> Detection:
        normalized = normalize(text)
        hits = [
            {"category": cat, "match": m.group()}
            for cat, pat in self.patterns.items()
            if (m := pat.search(normalized))
        ]
        if not hits:
            return Detection(triggered=False)
        return Detection(
            triggered=True,
            score=1.0,
            reason="Policy topics: " + ", ".join(h["category"] for h in hits),
            findings=hits,
        )
