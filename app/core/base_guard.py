"""The contract every guard implements. New guards subclass BaseGuard and
register themselves with @register_guard; no other code needs to change."""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from time import perf_counter
from typing import ClassVar

from app.core.context import RequestContext
from app.core.errors import PolicyError
from app.core.types import Action, Detection, FailMode, GuardResult

logger = logging.getLogger(__name__)


class BaseGuard(ABC):
    name: ClassVar[str] = "base"
    supports_redaction: ClassVar[bool] = False

    def __init__(
        self,
        action: Action = Action.BLOCK,
        fail_mode: FailMode = FailMode.CLOSED,
        timeout_s: float = 2.0,
        **params,
    ) -> None:
        if action == Action.REDACT and not self.supports_redaction:
            raise PolicyError(f"Guard '{self.name}' does not support action 'redact'")
        if action == Action.ALLOW:
            raise PolicyError("'allow' is not a valid guard action; disable the guard instead")
        self.action = action
        self.fail_mode = fail_mode
        self.timeout_s = timeout_s
        try:
            self.configure(**params)
        except TypeError as exc:
            raise PolicyError(f"Invalid params for guard '{self.name}': {exc}") from exc

    def configure(self) -> None:  # noqa: B027 - optional hook, not abstract
        """Subclasses override this with keyword arguments for their params."""

    @abstractmethod
    async def scan(self, text: str, ctx: RequestContext) -> Detection:
        """Inspect text and report what was found. Must not apply policy."""

    async def run(self, text: str, ctx: RequestContext) -> GuardResult:
        """Run the scan with timing, timeout, and fail-open/closed handling."""
        start = perf_counter()
        try:
            detection = await asyncio.wait_for(self.scan(text, ctx), timeout=self.timeout_s)
        except Exception as exc:  # noqa: BLE001 - a guard must never crash the gateway
            elapsed = (perf_counter() - start) * 1000
            error = "timeout" if isinstance(exc, asyncio.TimeoutError) else repr(exc)
            logger.warning("guard %s failed (%s), fail_mode=%s", self.name, error, self.fail_mode.value)
            closed = self.fail_mode == FailMode.CLOSED
            return GuardResult(
                guard=self.name,
                stage=ctx.stage,
                action=Action.BLOCK if closed else Action.ALLOW,
                triggered=closed,
                reason=f"guard error ({'fail-closed' if closed else 'fail-open'})",
                latency_ms=elapsed,
                error=error,
            )

        elapsed = (perf_counter() - start) * 1000
        action = self.action if detection.triggered else Action.ALLOW
        return GuardResult(
            guard=self.name,
            stage=ctx.stage,
            action=action,
            triggered=detection.triggered,
            score=detection.score,
            reason=detection.reason,
            findings=detection.findings,
            latency_ms=elapsed,
            output_text=detection.redacted_text if action == Action.REDACT else None,
        )
