#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import statistics
import random
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

from porter.candidates import publish, rebuild, settle


def percentile(values, fraction):
    ordered = sorted(values)
    return ordered[max(0, min(len(ordered) - 1, int(len(ordered) * fraction) - 1))]


def measure(strategy: str, count: int) -> dict:
    with tempfile.TemporaryDirectory(prefix=f"candidate-{strategy}-") as folder:
        root = Path(folder)
        (root / "acceptances").mkdir()
        inserts = []
        deletes = []
        with patch.dict(os.environ, {"PORTER_CANDIDATE_DURABILITY": strategy}):
            for number in range(count):
                value = {"package": f"PKG-{number:032x}", "kind": "demo.work"}
                began = time.perf_counter_ns()
                publish(root, value)
                inserts.append((time.perf_counter_ns() - began) / 1e6)
            for number in range(count):
                began = time.perf_counter_ns()
                settle(root, f"PKG-{number:032x}")
                deletes.append((time.perf_counter_ns() - began) / 1e6)
        def result(values):
            return {
                "median_ms": round(statistics.median(values), 3),
                "p95_ms": round(percentile(values, 0.95), 3),
                "p99_ms": round(percentile(values, 0.99), 3),
            }
        return {"strategy": strategy, "insert": result(inserts), "delete": result(deletes)}


def interleaved(count: int = 500) -> list[dict]:
    strategies = ("full", "relaxed", "grouped")
    temporary = {strategy: tempfile.TemporaryDirectory(prefix=f"candidate-{strategy}-") for strategy in strategies}
    roots = {strategy: Path(value.name) for strategy, value in temporary.items()}
    timings = {strategy: {"insert": [], "delete": []} for strategy in roots}
    try:
        for strategy, root in roots.items():
            (root / "acceptances").mkdir()
            with patch.dict(os.environ, {"PORTER_CANDIDATE_DURABILITY": strategy}):
                rebuild(root)
        randomizer = random.Random(1729)
        for operation in ("insert", "delete"):
            for number in range(count):
                order = list(strategies)
                randomizer.shuffle(order)
                for strategy in order:
                    with patch.dict(os.environ, {"PORTER_CANDIDATE_DURABILITY": strategy}):
                        began = time.perf_counter_ns()
                        if operation == "insert":
                            publish(roots[strategy], {"package": f"PKG-{number:032x}", "kind": "demo.work"})
                        else:
                            settle(roots[strategy], f"PKG-{number:032x}")
                        timings[strategy][operation].append((time.perf_counter_ns() - began) / 1e6)
        return [
            {
                "strategy": strategy,
                "insert": {
                    "median_ms": round(statistics.median(timings[strategy]["insert"]), 3),
                    "p95_ms": round(percentile(timings[strategy]["insert"], 0.95), 3),
                    "p99_ms": round(percentile(timings[strategy]["insert"], 0.99), 3),
                },
                "delete": {
                    "median_ms": round(statistics.median(timings[strategy]["delete"]), 3),
                    "p95_ms": round(percentile(timings[strategy]["delete"], 0.95), 3),
                    "p99_ms": round(percentile(timings[strategy]["delete"], 0.99), 3),
                },
            }
            for strategy in strategies
        ]
    finally:
        for value in temporary.values():
            value.cleanup()


if __name__ == "__main__":
    print(json.dumps(interleaved(), indent=2))
