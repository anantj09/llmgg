"""Runs an ordered set of guards over a piece of text.

Execution model:
  1. Detector guards (flag/block) run concurrently on the original text.
     Any BLOCK short-circuits the stage.
  2. Redactor guards run sequentially, each receiving the previous one's
     output, because they rewrite the text.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from time import perf_counter

from app.core.base_guard import BaseGuard
from app.core.context import RequestContext
from app.core.types import Action, GuardResult, Stage


@dataclass
class StageOutcome:
    text: str
    results: list[GuardResult] = field(default_factory=list)
    blocked_by: GuardResult | None = None
    latency_ms: float = 0.0

    @property
    def blocked(self) -> bool:
        return self.blocked_by is not None

    @property
    def triggered(self) -> list[str]:
        return [r.guard for r in self.results if r.triggered]


class GuardPipeline:
    def __init__(self, guards: list[BaseGuard], stage: Stage) -> None:
        self.stage = stage
        self.guards = guards
        self._detectors = [g for g in guards if g.action != Action.REDACT]
        self._redactors = [g for g in guards if g.action == Action.REDACT]

    def describe(self) -> list[dict]:
        return [
            {"type": g.name, "action": g.action.value, "fail_mode": g.fail_mode.value}
            for g in self.guards
        ]

    async def run(self, text: str, ctx: RequestContext) -> StageOutcome:
        start = perf_counter()
        ctx.stage = self.stage

        results = list(await asyncio.gather(*(g.run(text, ctx) for g in self._detectors)))
        blocked = next((r for r in results if r.action == Action.BLOCK), None)
        if blocked:
            return StageOutcome(text, results, blocked, (perf_counter() - start) * 1000)

        current = text
        for guard in self._redactors:
            result = await guard.run(current, ctx)
            results.append(result)
            if result.action == Action.BLOCK:  # a redactor that failed closed
                return StageOutcome(current, results, result, (perf_counter() - start) * 1000)
            if result.output_text is not None:
                current = result.output_text

        return StageOutcome(current, results, None, (perf_counter() - start) * 1000)
