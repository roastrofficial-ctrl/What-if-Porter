#!/usr/bin/env python3
from __future__ import annotations

import json
import statistics
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import porter.carriage as carriage
from porter.daemon import Porter
from porter.protocol import package


def summary(values):
    ordered = sorted(values)
    return {
        "median_ms": round(statistics.median(values), 3),
        "p95_ms": round(ordered[int(len(ordered) * 0.95) - 1], 3),
        "p99_ms": round(ordered[int(len(ordered) * 0.99) - 1], 3),
    }


def main():
    with tempfile.TemporaryDirectory(prefix="candidate-write-path-") as folder:
        root = Path(folder)
        porter = Porter("host", root, {})
        timings = {"canonical_ac": [], "inbox_projection": [], "candidate_projection": [], "deposit_total": []}
        original_atomic = carriage.atomic_json
        original_publish = carriage.publish

        def measured_atomic(path, value):
            began = time.perf_counter_ns()
            original_atomic(path, value)
            elapsed = (time.perf_counter_ns() - began) / 1e6
            if path.parent.name == "acceptances":
                timings["canonical_ac"].append(elapsed)
            elif path.parent.name == "inbox":
                timings["inbox_projection"].append(elapsed)

        def measured_publish(path, value):
            began = time.perf_counter_ns()
            result = original_publish(path, value)
            timings["candidate_projection"].append((time.perf_counter_ns() - began) / 1e6)
            return result

        with patch.object(carriage, "atomic_json", measured_atomic), patch.object(carriage, "publish", measured_publish):
            for number in range(500):
                value = package("sender", "host", "demo.work", {"n": number})
                began = time.perf_counter_ns()
                porter.deposit(value)
                timings["deposit_total"].append((time.perf_counter_ns() - began) / 1e6)
        print(json.dumps({name: summary(values) for name, values in timings.items()}, indent=2))


if __name__ == "__main__":
    main()
