"""The orchestration layer: input guards -> provider -> output guards -> audit log.

This is the only place that knows the order of operations. Routes stay thin,
guards stay unaware of HTTP, and providers stay unaware of guards.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any

from app.api.schemas import ChatCompletionRequest
from app.config import Settings
from app.core.context import RequestContext
from app.core.errors import UpstreamError
from app.core.pipeline import GuardPipeline, StageOutcome
from app.core.policy import Policy, build_pipeline
from app.core.types import Stage
from app.observability.cost import estimate_cost, estimate_tokens
from app.observability.store import EventStore
from app.providers.base import ChatProvider

logger = logging.getLogger(__name__)

WITHHELD_MESSAGE = "This response was withheld by the guardrail gateway because it violated the output policy."


@dataclass
class GatewayResponse:
    status_code: int
    body: dict[str, Any]
    headers: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class _ActivePolicy:
    policy: Policy
    input_pipeline: GuardPipeline
    output_pipeline: GuardPipeline


class GuardrailGateway:
    def __init__(self, settings: Settings, policy: Policy, provider: ChatProvider, store: EventStore):
        self.settings = settings
        self.provider = provider
        self.store = store
        self._active = self._compile(policy)

    # ---- policy management -------------------------------------------------
    @staticmethod
    def _compile(policy: Policy) -> _ActivePolicy:
        return _ActivePolicy(
            policy=policy,
            input_pipeline=build_pipeline(policy.input, Stage.INPUT),
            output_pipeline=build_pipeline(policy.output, Stage.OUTPUT),
        )

    def reload_policy(self, policy: Policy) -> None:
        """Build the new pipelines fully, then swap in one assignment, so
        in-flight requests keep the policy they started with."""
        self._active = self._compile(policy)

    def describe_policy(self) -> dict[str, Any]:
        a = self._active
        return {
            "scan_roles": a.policy.scan_roles,
            "restore_pii_in_output": a.policy.restore_pii_in_output,
            "input": a.input_pipeline.describe(),
            "output": a.output_pipeline.describe(),
        }

    # ---- request handling --------------------------------------------------
    async def handle_chat(self, req: ChatCompletionRequest, debug: bool = False) -> GatewayResponse:
        active = self._active  # pin the policy for the whole request
        request_id = f"req_{uuid.uuid4().hex[:16]}"
        ctx = RequestContext(request_id=request_id)
        started = perf_counter()
        model = req.model or self.settings.default_model
        headers = {"X-Request-ID": request_id}

        if req.stream:
            return GatewayResponse(400, _error("Streaming is not supported: output guards need the full response.",
                                               "invalid_request_error", "stream_unsupported"), headers)

        # 1) Input guards, per message in the scanned roles
        messages = [m.model_dump(exclude_none=True) for m in req.messages]
        input_results = []
        guard_ms = 0.0
        for msg in messages:
            content = msg.get("content")
            if msg.get("role") not in active.policy.scan_roles or not isinstance(content, str):
                continue
            outcome = await active.input_pipeline.run(content, ctx)
            guard_ms += outcome.latency_ms
            input_results.extend(outcome.results)
            if outcome.blocked:
                return await self._blocked_input(request_id, model, messages, outcome, input_results,
                                                  guard_ms, started, headers)
            msg["content"] = outcome.text

        # 2) Upstream call
        llm_start = perf_counter()
        try:
            upstream = await self.provider.complete(messages, model, req.passthrough_params())
        except UpstreamError as exc:
            logger.error("upstream failure %s: %s", request_id, exc)
            await self._record(request_id, model, "upstream_error", input_results, [], guard_ms,
                               (perf_counter() - llm_start) * 1000, started, messages, 0, 0)
            headers["X-Guardrail-Status"] = "upstream_error"
            return GatewayResponse(502, _error("The upstream LLM provider failed.", "upstream_error",
                                               "upstream_error"), headers)
        llm_ms = (perf_counter() - llm_start) * 1000

        # 3) Output guards
        out = await active.output_pipeline.run(upstream.content, ctx)
        guard_ms += out.latency_ms
        if out.blocked:
            status, content, finish = "blocked_output", WITHHELD_MESSAGE, "content_filter"
        else:
            status, finish = "allowed", upstream.finish_reason
            content = ctx.restore(out.text) if active.policy.restore_pii_in_output else out.text

        prompt_tokens = upstream.prompt_tokens or estimate_tokens(" ".join(str(m.get("content", "")) for m in messages))
        completion_tokens = upstream.completion_tokens or estimate_tokens(upstream.content)
        cost = await self._record(request_id, model, status, input_results, out.results, guard_ms, llm_ms,
                                  started, messages, prompt_tokens, completion_tokens)

        total_ms = (perf_counter() - started) * 1000
        guardrails = {
            "request_id": request_id,
            "status": status,
            "input": [r.to_dict() for r in input_results],
            "output": [r.to_dict() for r in out.results],
            "latency_ms": {"total": round(total_ms, 2), "guards": round(guard_ms, 3), "llm": round(llm_ms, 2)},
            "estimated_cost_usd": round(cost, 8),
        }
        if debug:
            guardrails["upstream_messages"] = messages        # exactly what the LLM saw
            guardrails["raw_model_output"] = out.text if not out.blocked else None
        headers["X-Guardrail-Status"] = status
        body = {
            "id": f"chatcmpl-{request_id}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": upstream.model,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": finish}],
            "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
                      "total_tokens": prompt_tokens + completion_tokens},
            "guardrails": guardrails,
        }
        return GatewayResponse(200, body, headers)

    # ---- helpers -----------------------------------------------------------
    async def _blocked_input(self, request_id, model, messages, outcome: StageOutcome, input_results,
                             guard_ms, started, headers) -> GatewayResponse:
        await self._record(request_id, model, "blocked_input", input_results, [], guard_ms, 0.0,
                           started, messages, 0, 0)
        blocker = outcome.blocked_by
        headers["X-Guardrail-Status"] = "blocked_input"
        body = _error(f"Request blocked by guard '{blocker.guard}': {blocker.reason or 'policy violation'}",
                      "guardrail_violation", blocker.guard)
        body["guardrails"] = {
            "request_id": request_id,
            "status": "blocked_input",
            "input": [r.to_dict() for r in input_results],
            "output": [],
            "latency_ms": {
                "total": round((perf_counter() - started) * 1000, 2),
                "guards": round(guard_ms, 3),
                "llm": 0,
            },
        }
        return GatewayResponse(400, body, headers)

    async def _record(self, request_id, model, status, input_results, output_results, guard_ms, llm_ms,
                      started, messages, prompt_tokens, completion_tokens) -> float:
        cost = estimate_cost(prompt_tokens, completion_tokens,
                             self.settings.cost_per_1k_input, self.settings.cost_per_1k_output)
        last_user = next((m.get("content") for m in reversed(messages) if m.get("role") == "user"), "") or ""
        triggered = sorted({f"{r.stage.value}:{r.guard}" for r in [*input_results, *output_results] if r.triggered})
        event = {
            "id": request_id,
            "ts": time.time(),
            "model": model,
            "status": status,
            "triggered": triggered,
            "total_ms": (perf_counter() - started) * 1000,
            "guard_ms": guard_ms,
            "llm_ms": llm_ms,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "cost_usd": cost,
            # For a blocked request, the message may not have been redacted yet,
            # so only the redacted preview of allowed requests is stored.
            "prompt_preview": last_user[:300] if status != "blocked_input" else "[withheld: request blocked]",
            "details": {"results": [r.to_dict() for r in [*input_results, *output_results] if r.triggered]},
        }
        try:
            await self.store.record(event)
        except Exception:  # noqa: BLE001 - logging must never break serving
            logger.exception("failed to record audit event %s", request_id)
        return cost


def _error(message: str, type_: str, code: str) -> dict[str, Any]:
    return {"error": {"message": message, "type": type_, "code": code}}
