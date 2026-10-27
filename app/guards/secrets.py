"""Detects credentials: cloud keys, API tokens, private keys, JWTs, password assignments."""

from __future__ import annotations

import math
import re
from collections import Counter

from app.core.base_guard import BaseGuard
from app.core.context import RequestContext
from app.core.registry import register_guard
from app.core.types import Detection
from app.guards._text import Span, replace_spans, select_non_overlapping

_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("PRIVATE_KEY", re.compile(
        r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----[\s\S]*?"
        r"(?:-----END (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----|$)")),
    ("AWS_ACCESS_KEY", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("GITHUB_TOKEN", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{40,})\b")),
    ("OPENAI_STYLE_KEY", re.compile(r"\bsk-(?:proj-|ant-)?[A-Za-z0-9_-]{20,}")),
    ("SLACK_TOKEN", re.compile(r"\bxox[abpors]-[A-Za-z0-9-]{10,}\b")),
    ("GOOGLE_API_KEY", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")),
]

_ASSIGNMENT = re.compile(
    r"(?i)\b(password|passwd|pwd|secret|api[_-]?key|access[_-]?token|auth[_-]?token)\b"
    r"\s*[:=]\s*['\"]?([^\s'\"]{8,})"
)


def shannon_entropy(value: str) -> float:
    counts = Counter(value)
    n = len(value)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


def find_secrets(text: str, min_entropy: float) -> list[Span]:
    candidates: list[tuple[int, Span]] = []
    for label, pattern in _PATTERNS:
        for m in pattern.finditer(text):
            candidates.append((0, Span(m.start(), m.end(), label, m.group())))
    for m in _ASSIGNMENT.finditer(text):
        value = m.group(2)
        if shannon_entropy(value) >= min_entropy:  # skip "password = changeme"-style text
            candidates.append((1, Span(m.start(2), m.end(2), "ASSIGNED_SECRET", value)))
    return select_non_overlapping(candidates)


@register_guard
class SecretsGuard(BaseGuard):
    name = "secrets"
    supports_redaction = True

    def configure(self, min_entropy: float = 3.0) -> None:
        self.min_entropy = min_entropy

    async def scan(self, text: str, ctx: RequestContext) -> Detection:
        spans = find_secrets(text, self.min_entropy)
        if not spans:
            return Detection(triggered=False)
        labels = sorted({s.label for s in spans})
        return Detection(
            triggered=True,
            score=1.0,
            reason="Credential detected: " + ", ".join(labels),
            findings=[{"type": s.label, "start": s.start, "end": s.end} for s in spans],
            # Secrets are never restorable, even to the caller.
            redacted_text=replace_spans(text, spans, lambda s: f"[REDACTED_{s.label}]"),
        )
