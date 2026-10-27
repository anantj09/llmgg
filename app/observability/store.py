"""Audit-event store on SQLite. Only redacted text is ever written here.

SQLite keeps the project dependency-free and deployable on a free tier.
Swapping to Postgres means re-implementing these four methods.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    ts REAL NOT NULL,
    model TEXT,
    status TEXT NOT NULL,
    triggered TEXT NOT NULL,
    total_ms REAL,
    guard_ms REAL,
    llm_ms REAL,
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    cost_usd REAL,
    prompt_preview TEXT,
    details TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);
"""

_COLUMNS = [
    "id", "ts", "model", "status", "triggered", "total_ms", "guard_ms", "llm_ms",
    "prompt_tokens", "completion_tokens", "cost_usd", "prompt_preview", "details",
]


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    k = (len(ordered) - 1) * pct
    lo, hi = int(k), min(int(k) + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo)


class EventStore:
    def __init__(self, path: str) -> None:
        self.path = path
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def init(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def _insert(self, event: dict[str, Any]) -> None:
        row = {**event, "triggered": json.dumps(event["triggered"]), "details": json.dumps(event["details"])}
        placeholders = ", ".join("?" for _ in _COLUMNS)
        with self._connect() as conn:
            conn.execute(
                f"INSERT INTO events ({', '.join(_COLUMNS)}) VALUES ({placeholders})",
                [row.get(c) for c in _COLUMNS],
            )

    def _recent(self, limit: int) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM events ORDER BY ts DESC LIMIT ?", (limit,)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["triggered"] = json.loads(d["triggered"])
            d["details"] = json.loads(d["details"] or "{}")
            out.append(d)
        return out

    async def record(self, event: dict[str, Any]) -> None:
        await asyncio.to_thread(self._insert, event)

    async def recent(self, limit: int = 50) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._recent, limit)

    async def stats(self, window: int = 2000) -> dict[str, Any]:
        events = await self.recent(window)
        by_status: dict[str, int] = {}
        by_guard: dict[str, int] = {}
        for e in events:
            by_status[e["status"]] = by_status.get(e["status"], 0) + 1
            for g in e["triggered"]:
                by_guard[g] = by_guard.get(g, 0) + 1
        total = len(events)
        blocked = by_status.get("blocked_input", 0) + by_status.get("blocked_output", 0)
        guard_ms = [e["guard_ms"] or 0 for e in events]
        total_ms = [e["total_ms"] or 0 for e in events]
        return {
            "window": total,
            "requests": total,
            "by_status": by_status,
            "block_rate": round(blocked / total, 4) if total else 0.0,
            "guard_triggers": dict(sorted(by_guard.items(), key=lambda kv: -kv[1])),
            "latency_ms": {
                "guard_p50": round(_percentile(guard_ms, 0.5), 3),
                "guard_p95": round(_percentile(guard_ms, 0.95), 3),
                "total_p50": round(_percentile(total_ms, 0.5), 2),
                "total_p95": round(_percentile(total_ms, 0.95), 2),
            },
            "tokens": {
                "prompt": sum(e["prompt_tokens"] or 0 for e in events),
                "completion": sum(e["completion_tokens"] or 0 for e in events),
            },
            "cost_usd": round(sum(e["cost_usd"] or 0 for e in events), 6),
        }
