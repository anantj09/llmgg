"""Text helpers shared by guards."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass

_ZERO_WIDTH = re.compile(r"[\u200b-\u200f\u2060\ufeff]")
_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class Span:
    start: int
    end: int
    label: str
    value: str


def normalize(text: str) -> str:
    """Defeat simple obfuscation: unicode look-alikes, zero-width chars, odd spacing."""
    text = unicodedata.normalize("NFKC", text)
    text = _ZERO_WIDTH.sub("", text)
    return _WHITESPACE.sub(" ", text).strip().lower()


def select_non_overlapping(spans: list[tuple[int, Span]]) -> list[Span]:
    """Given (priority, span) pairs, keep the highest-priority span wherever two overlap."""
    chosen: list[Span] = []
    for _, span in sorted(spans, key=lambda p: (p[0], p[1].start)):
        if all(span.end <= c.start or span.start >= c.end for c in chosen):
            chosen.append(span)
    return sorted(chosen, key=lambda s: s.start)


def replace_spans(text: str, spans: list[Span], replacer: Callable[[Span], str]) -> str:
    """Replace non-overlapping spans. Replacements are computed left-to-right
    (so placeholders number in reading order), then applied right-to-left so
    earlier offsets stay valid."""
    ordered = sorted(spans, key=lambda s: s.start)
    replacements = [(span, replacer(span)) for span in ordered]
    for span, new in reversed(replacements):
        text = text[: span.start] + new + text[span.end :]
    return text
