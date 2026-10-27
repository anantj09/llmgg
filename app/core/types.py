"""Core value types shared by guards, the pipeline, and the gateway service."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Action(StrEnum):
    ALLOW = "allow"    # nothing found, or finding ignored
    FLAG = "flag"      # log the finding but let the request through
    REDACT = "redact"  # rewrite the text, then continue
    BLOCK = "block"    # stop the request


class Stage(StrEnum):
    INPUT = "input"
    OUTPUT = "output"


class FailMode(StrEnum):
    OPEN = "open"      # if the guard crashes, let traffic through
    CLOSED = "closed"  # if the guard crashes, block traffic


@dataclass(slots=True)
class Detection:
    """What a guard found in a piece of text (before policy is applied)."""

    triggered: bool
    score: float = 0.0
    reason: str = ""
    findings: list[dict[str, Any]] = field(default_factory=list)
    redacted_text: str | None = None


@dataclass(slots=True)
class GuardResult:
    """A guard's detection after its policy action has been applied."""

    guard: str
    stage: Stage
    action: Action
    triggered: bool
    score: float = 0.0
    reason: str = ""
    findings: list[dict[str, Any]] = field(default_factory=list)
    latency_ms: float = 0.0
    error: str | None = None
    output_text: str | None = None  # rewritten text when action == REDACT

    def to_dict(self) -> dict[str, Any]:
        return {
            "guard": self.guard,
            "stage": self.stage.value,
            "action": self.action.value,
            "triggered": self.triggered,
            "score": round(self.score, 3),
            "reason": self.reason,
            "findings": self.findings,
            "latency_ms": round(self.latency_ms, 3),
            "error": self.error,
        }
