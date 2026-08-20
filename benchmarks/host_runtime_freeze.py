#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import resource
import statistics
import sys
import tempfile
import time
from pathlib import Path

from porter.candidates import rebuild
from porter.host_runtime import HostRuntime


class TrivialAdapter:
    def __init__(self, delay_ms: int = 0):
        self.delay_ms = delay_ms
        self.invocations = 0

    def dispatch(self, dispatch_id, collection):
        self.invocations += 1
        if self.delay_ms:
            time.sleep(self.delay_ms / 1000)
        return {
            "contract": "PORTER-HOST-ADAPTER/1",
            "dispatch": dispatch_id,
            "runtime_observation": "ADAPTER_RETURNED_CONTROL",
        }

    def close(self):
        pass


def populate(root: Path, total: int):
    inbox = root / "inbox"
    acceptances = root / "acceptances"
    inbox.mkdir(parents=True)
    acceptances.mkdir(parents=True)
    for number in range(total):
        package_id = f"PKG-{number:032x}"
        package = {
            "protocol": "PORTER/1", "package": package_id, "from": "sender",
            "to": "tiny-host", "kind": "tiny.observe", "created": 1,
            "expires": 4102444800, "payload": {"n": number},
        }
        acceptance = {
            "protocol": "PORTER/1", "kind": "REMOTE_ACCEPTANCE",
            "acceptance": f"AC-{number:032x}", "recipient": "tiny-host",
            "package": package, "package_digest": f"sha256:{number:064x}",
            "accepted_at_ms": number,
        }
        (inbox / f"{package_id}.json").write_text(json.dumps(package, separators=(",", ":")))
        (acceptances / f"{package_id}.json").write_text(json.dumps(acceptance, separators=(",", ":")))
    rebuild(root)


def percentiles(values):
    if not values:
        return {"median_ms": None, "p95_ms": None, "p99_ms": None}
    ordered = sorted(values)
    return {
        "median_ms": round(statistics.median(ordered), 3),
        "p95_ms": round(ordered[max(0, int(len(ordered) * .95) - 1)], 3),
        "p99_ms": round(ordered[max(0, int(len(ordered) * .99) - 1)], 3),
    }


def trial(total: int, batch: int, delay_ms: int):
    with tempfile.TemporaryDirectory(prefix="porter-runtime-freeze-") as folder:
        root = Path(folder)
        populate(root, total)
        adapter = TrivialAdapter(delay_ms)
        journal = root / "runtime.jsonl"
        runtime = HostRuntime(root, "tiny-host", adapter, {"tiny.observe"}, batch, 100, journal)
        began = time.perf_counter_ns()
        visits = 0
        dispatched = 0
        empty_ms = None
        while dispatched < total:
            count = runtime.visit()
            visits += 1
            dispatched += count
        drain_ms = (time.perf_counter_ns() - began) / 1e6
        began_empty = time.perf_counter_ns()
        assert runtime.visit() == 0
        empty_ms = (time.perf_counter_ns() - began_empty) / 1e6
        observations = [json.loads(line) for line in journal.read_text().splitlines()] if journal.exists() else []
        returned = [value for value in observations if value["observation"] == "ADAPTER_RETURNED_CONTROL"]
        ended = [value for value in observations if value["observation"] == "VISIT_ENDED"]
        collection = [
            value["collection_ms"] for value in observations
            if value["observation"] == "DISPATCH_BEGAN"
        ]
        dispatch = [value["dispatch_ms"] for value in returned]
        inspection = [value["inspection_ms"] for value in ended]
        return {
            "candidates": total, "batch_size": batch, "adapter_delay_ms": delay_ms,
            "visits": visits, "dispatched": dispatched,
            "drain_ms": round(drain_ms, 3),
            "throughput_per_s": round(total / (drain_ms / 1000), 2) if total else None,
            "empty_attention_ms": round(empty_ms, 3),
            "inspection": percentiles(inspection),
            "collection": percentiles(collection),
            "dispatch_including_adapter": percentiles(dispatch),
            "rss_kib": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 if sys.platform == "darwin" else 1)),
        }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sizes", default="0,1,100,1000")
    parser.add_argument("--output")
    args = parser.parse_args()
    results = []
    for total in [int(value) for value in args.sizes.split(",")]:
        results.append(trial(total, min(100, max(1, total)), 0))
    for batch in (1, 10, 100):
        results.append(trial(1000, batch, 0))
    for delay in (10, 100, 1000, 10_000):
        results.append(trial(1 if delay == 10_000 else 10, 10, delay))
    value = {"schema": "PORTER-HOST-RUNTIME-FREEZE-PRESSURE/1", "results": results}
    rendered = json.dumps(value, indent=2)
    print(rendered)
    if args.output:
        Path(args.output).write_text(rendered + "\n")


if __name__ == "__main__":
    main()
