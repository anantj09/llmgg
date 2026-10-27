"""Heuristic prompt-injection / jailbreak detector.

Each matching signal contributes a weight; weights are combined with a
noisy-OR (1 - prod(1 - w)) so several weak signals can add up to a block,
but one weak signal alone cannot. The guard is deliberately transparent:
every block lists the signals that fired, which matters for audits.

To plug in an ML classifier, subclass BaseGuard with the same `name`
pattern and register it; the policy picks which one to use.
"""

from __future__ import annotations

import re

from app.core.base_guard import BaseGuard
from app.core.context import RequestContext
from app.core.registry import register_guard
from app.core.types import Detection
from app.guards._text import normalize

_P = r"(?:previous|prior|above|earlier|preceding|original|all|any|your|the|these|those)"
_I = r"(?:instructions?|rules?|prompts?|directions?|guidelines?|polic(?:y|ies)|constraints?)"

SIGNALS: list[tuple[str, float, re.Pattern[str]]] = [
    ("override_instructions", 0.9, re.compile(
        rf"\b(?:ignore|disregard|forget|override|skip|drop)\b(?:\s+\w+){{0,3}}?\s+{_P}(?:\s+\w+){{0,2}}?\s+{_I}")),
    ("new_instructions", 0.55, re.compile(r"\b(?:new|updated|real|actual)\s+(?:system\s+)?instructions?\s*:")),
    ("reveal_system_prompt", 0.85, re.compile(
        r"\b(?:reveal|show|print|repeat|output|display|leak|dump|tell me|what (?:is|are))\b"
        r"(?:\s+me)?\s+(?:your|the)\s+(?:full\s+|entire\s+|original\s+|hidden\s+|initial\s+|exact\s+)?"
        r"(?:system\s+prompt|system\s+message|initial\s+instructions|hidden\s+instructions|"
        r"instructions\s+you\s+were\s+given|prompt\s+above)")),
    ("persona_jailbreak", 0.8, re.compile(
        r"\b(?:dan|do anything now|developer mode|jailbreak(?:ed)?|god mode|unfiltered mode|evil confidant)\b")),
    ("unrestricted_roleplay", 0.7, re.compile(
        r"\b(?:pretend|act|imagine|roleplay|behave)\b.{0,40}\b(?:no|without|free (?:of|from))\s+"
        r"(?:any\s+)?(?:restrictions?|rules?|filters?|limits?|limitations|guidelines|censorship|ethics)")),
    ("you_are_now", 0.45, re.compile(r"\byou are (?:now|no longer)\b")),
    ("bypass_safety", 0.75, re.compile(
        r"\b(?:bypass|disable|turn off|circumvent|get around|evade)\b.{0,25}\b"
        r"(?:safety|filters?|guardrails?|restrictions?|content polic(?:y|ies)|moderation)")),
    ("fake_role_marker", 0.5, re.compile(
        r"(?:^|\s)(?:system|assistant)\s*:\s|<\|im_start\|>|<\|system\|>|\[/?inst\]|###\s*(?:system|instruction)")),
    ("encoded_payload", 0.35, re.compile(r"\b(?:decode|base64|rot13)\b.{0,40}\b(?:execute|follow|run|obey)\b")),
]

_BASE64_BLOB = re.compile(r"[A-Za-z0-9+/]{120,}={0,2}")


def score_text(text: str) -> tuple[float, list[dict]]:
    normalized = normalize(text)
    hits: list[dict] = []
    for name, weight, pattern in SIGNALS:
        if pattern.search(normalized):
            hits.append({"signal": name, "weight": weight})
    if _BASE64_BLOB.search(text):  # case-sensitive, on raw text
        hits.append({"signal": "long_base64_blob", "weight": 0.3})

    remaining = 1.0
    for h in hits:
        remaining *= 1.0 - h["weight"]
    return 1.0 - remaining, hits


@register_guard
class PromptInjectionGuard(BaseGuard):
    name = "prompt_injection"

    def configure(self, threshold: float = 0.7) -> None:
        if not 0 < threshold <= 1:
            raise TypeError("threshold must be in (0, 1]")
        self.threshold = threshold

    async def scan(self, text: str, ctx: RequestContext) -> Detection:
        score, hits = score_text(text)
        triggered = score >= self.threshold
        reason = ""
        if hits:
            reason = "Signals: " + ", ".join(h["signal"] for h in hits)
        return Detection(triggered=triggered, score=score, reason=reason, findings=hits)
