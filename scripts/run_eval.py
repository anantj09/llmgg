"""Benchmarks the guardrails: detection quality and latency overhead.

    python scripts/run_eval.py [--threshold 0.7]

Prints precision/recall/F1 for prompt injection, PII recall on a labelled
set, and p50/p95 latency of the full input pipeline.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app.guards  # noqa: E402,F401
from app.core.context import RequestContext  # noqa: E402
from app.core.policy import build_pipeline, load_policy  # noqa: E402
from app.core.types import Stage  # noqa: E402
from app.guards.pii import ALL_ENTITIES, find_pii  # noqa: E402
from app.guards.prompt_injection import score_text  # noqa: E402

PII_CASES = [
    ("Reach me at priya.k@outlook.com", {"EMAIL"}),
    ("My number is 9876543210", {"PHONE"}),
    ("Call +91-98250-12345 after 6", {"PHONE"}),
    ("US office: (212) 555-0198", {"PHONE"}),
    ("Card: 5555 5555 5555 4444 exp 09/28", {"CREDIT_CARD"}),
    ("Amex 3782 822463 10005", {"CREDIT_CARD"}),
    ("PAN is BNZPM2501F", {"PAN"}),
    ("SSN 078-05-1120", {"SSN"}),
    ("Server at 172.16.254.1 is down", {"IP_ADDRESS"}),
    ("Aadhaar 2345 6789 0124 please verify", {"AADHAAR"}),
    ("Write to a.b@c.io or call 9123456780", {"EMAIL", "PHONE"}),
    ("Order #4111 1111 1111 1112 shipped", set()),   # fails Luhn
    ("Build 1.2.3.400 released", set()),             # invalid IP (octet > 255)
    ("Meeting at 10:30 in room 204", set()),
    ("The year 2024 had 366 days", set()),
]


def eval_injection(threshold: float) -> dict:
    rows = [json.loads(line) for line in (ROOT / "evals/injection_eval.jsonl").read_text().splitlines()]
    tp = fp = fn = tn = 0
    misses, false_alarms = [], []
    for r in rows:
        score, _ = score_text(r["text"])
        pred = int(score >= threshold)
        if pred and r["label"]:
            tp += 1
        elif pred and not r["label"]:
            fp += 1
            false_alarms.append(r["text"])
        elif not pred and r["label"]:
            fn += 1
            misses.append(r["text"])
        else:
            tn += 1
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"n": len(rows), "tp": tp, "fp": fp, "fn": fn, "tn": tn, "precision": precision,
            "recall": recall, "f1": f1, "misses": misses, "false_alarms": false_alarms}


def eval_pii() -> dict:
    exact = 0
    expected_total = found_total = 0
    for text, expected in PII_CASES:
        found = {s.label for s in find_pii(text, set(ALL_ENTITIES))}
        exact += int(found == expected)
        expected_total += len(expected)
        found_total += len(found & expected)
    return {"cases": len(PII_CASES), "exact_match": exact / len(PII_CASES),
            "entity_recall": found_total / expected_total}


async def eval_latency(iterations: int = 2000) -> dict:
    pipeline = build_pipeline(load_policy(ROOT / "policies/default.yaml").input, Stage.INPUT)
    sample = ("Hi, I'm Riya (riya.shah@gmail.com, +91 98765 43210). My card 4111 1111 1111 1111 "
              "was charged twice. Can you help me write a complaint to the bank? ") * 3
    timings = []
    for i in range(iterations):
        start = perf_counter()
        await pipeline.run(sample, RequestContext(f"bench-{i}"))
        timings.append((perf_counter() - start) * 1000)
    timings.sort()
    return {"iterations": iterations, "chars": len(sample), "p50_ms": statistics.median(timings),
            "p95_ms": timings[int(0.95 * len(timings)) - 1], "p99_ms": timings[int(0.99 * len(timings)) - 1]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--threshold", type=float, default=0.7)
    args = parser.parse_args()

    inj = eval_injection(args.threshold)
    pii = eval_pii()
    lat = asyncio.run(eval_latency())

    print(f"\nPrompt injection (threshold={args.threshold}, n={inj['n']})")
    print(f"  precision {inj['precision']:.2%}   recall {inj['recall']:.2%}   F1 {inj['f1']:.2%}")
    print(f"  TP {inj['tp']}  FP {inj['fp']}  FN {inj['fn']}  TN {inj['tn']}")
    if inj["misses"]:
        print("  missed attacks:")
        for m in inj["misses"]:
            print(f"    - {m}")
    if inj["false_alarms"]:
        print("  false alarms:")
        for m in inj["false_alarms"]:
            print(f"    - {m}")
    print(f"\nPII detection (n={pii['cases']})")
    print(f"  exact-match {pii['exact_match']:.2%}   entity recall {pii['entity_recall']:.2%}")
    print(f"\nInput pipeline latency ({lat['iterations']} runs, {lat['chars']} chars)")
    print(f"  p50 {lat['p50_ms']:.3f} ms   p95 {lat['p95_ms']:.3f} ms   p99 {lat['p99_ms']:.3f} ms\n")


if __name__ == "__main__":
    main()
