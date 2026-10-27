"""PII detection and reversible redaction.

On INPUT, each value is swapped for a stable placeholder (<EMAIL_1>) and kept
in the request vault, so the LLM never sees it but the caller can get it back.
On OUTPUT, values are masked permanently ([EMAIL]) because they came from the
model, not the caller.
"""

from __future__ import annotations

import ipaddress
import re

from app.core.base_guard import BaseGuard
from app.core.context import RequestContext
from app.core.registry import register_guard
from app.core.types import Detection, Stage
from app.guards._checksums import luhn_valid, verhoeff_valid
from app.guards._text import Span, replace_spans, select_non_overlapping

# (entity, priority, pattern, validator). Lower priority number wins overlaps,
# so checksum-validated entities beat looser patterns like PHONE.
_PATTERNS: list[tuple[str, int, re.Pattern[str], object]] = [
    ("EMAIL", 0, re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), None),
    ("CREDIT_CARD", 1, re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)"),
     lambda v: luhn_valid(re.sub(r"\D", "", v))),
    ("AADHAAR", 2, re.compile(r"(?<!\d)[2-9]\d{3}[ -]?\d{4}[ -]?\d{4}(?!\d)"),
     lambda v: verhoeff_valid(re.sub(r"\D", "", v))),
    ("PAN", 3, re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b"), None),
    ("SSN", 4, re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), None),
    ("IP_ADDRESS", 5, re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), lambda v: _valid_ip(v)),
    ("PHONE", 6, re.compile(
        r"(?<![\w+])(?:\+91[ -]?|0)?[6-9]\d{4}[ -]?\d{5}(?!\d)"          # India
        r"|(?<![\w+])(?:\+1[ -]?)?\(?\d{3}\)?[ .-]\d{3}[ .-]\d{4}(?!\d)"  # US/CA
        r"|(?<![\w])\+\d{1,3}[ -]?\d{2,4}[ -]?\d{3,4}[ -]?\d{3,4}(?!\d)"  # other intl
    ), None),
]

ALL_ENTITIES = [p[0] for p in _PATTERNS]


def _valid_ip(value: str) -> bool:
    try:
        ipaddress.IPv4Address(value)
        return True
    except ValueError:
        return False


def find_pii(text: str, entities: set[str]) -> list[Span]:
    candidates: list[tuple[int, Span]] = []
    for entity, priority, pattern, validator in _PATTERNS:
        if entity not in entities:
            continue
        for m in pattern.finditer(text):
            if validator is None or validator(m.group()):
                candidates.append((priority, Span(m.start(), m.end(), entity, m.group())))
    return select_non_overlapping(candidates)


@register_guard
class PIIGuard(BaseGuard):
    name = "pii"
    supports_redaction = True

    def configure(self, entities: list[str] | None = None) -> None:
        requested = set(entities or ALL_ENTITIES)
        unknown = requested - set(ALL_ENTITIES)
        if unknown:
            raise TypeError(f"unknown PII entities {sorted(unknown)}")
        self.entities = requested

    async def scan(self, text: str, ctx: RequestContext) -> Detection:
        spans = find_pii(text, self.entities)
        if not spans:
            return Detection(triggered=False)

        if ctx.stage == Stage.INPUT:
            redacted = replace_spans(text, spans, lambda s: ctx.placeholder_for(s.label, s.value))
        else:
            redacted = replace_spans(text, spans, lambda s: f"[{s.label}]")

        counts: dict[str, int] = {}
        for s in spans:
            counts[s.label] = counts.get(s.label, 0) + 1
        return Detection(
            triggered=True,
            score=1.0,
            reason="PII detected: " + ", ".join(f"{k} x{v}" for k, v in sorted(counts.items())),
            # Never log raw values, only types and positions.
            findings=[{"type": s.label, "start": s.start, "end": s.end} for s in spans],
            redacted_text=redacted,
        )
