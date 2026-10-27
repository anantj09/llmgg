import asyncio
import time

from app.observability.cost import estimate_cost, estimate_tokens
from app.observability.store import EventStore, _percentile


def _event(i, status="allowed", triggered=None, guard_ms=1.0):
    return {
        "id": f"req_{i}", "ts": time.time() + i, "model": "m", "status": status,
        "triggered": triggered or [], "total_ms": 100.0 + i, "guard_ms": guard_ms, "llm_ms": 90.0,
        "prompt_tokens": 10, "completion_tokens": 5, "cost_usd": 0.001,
        "prompt_preview": "hello <EMAIL_1>", "details": {},
    }


def test_store_records_and_aggregates(tmp_path):
    store = EventStore(str(tmp_path / "events.db"))
    store.init()

    async def scenario():
        await store.record(_event(1))
        await store.record(_event(2, "blocked_input", ["input:prompt_injection"]))
        await store.record(_event(3, triggered=["input:pii"]))
        await store.record(_event(4, triggered=["input:pii"]))
        return await store.recent(10), await store.stats()

    recent, stats = asyncio.run(scenario())
    assert [e["id"] for e in recent] == ["req_4", "req_3", "req_2", "req_1"]  # newest first
    assert stats["requests"] == 4
    assert stats["block_rate"] == 0.25
    assert stats["guard_triggers"] == {"input:pii": 2, "input:prompt_injection": 1}
    assert stats["tokens"] == {"prompt": 40, "completion": 20}


def test_percentile_interpolates():
    assert _percentile([], 0.5) == 0.0
    assert _percentile([1, 2, 3, 4], 0.5) == 2.5
    assert _percentile([10], 0.95) == 10


def test_cost_helpers():
    assert estimate_tokens("abcd" * 10) == 10
    assert abs(estimate_cost(1000, 1000, 0.1, 0.2) - 0.3) < 1e-9
