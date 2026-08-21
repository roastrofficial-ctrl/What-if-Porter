#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
import threading
import time
from pathlib import Path

from opportunity_scheduling import MeasuredAdapter, populate, trial
from porter.opportunities import ElasticOpportunityRuntime


def elastic_trial(total: int, delay_ms: int, startup_ms: int = 45) -> dict:
    with tempfile.TemporaryDirectory(prefix="porter-elastic-") as folder:
        root = Path(folder)
        populate(root, total)
        records, lock = [], threading.Lock()

        def factory():
            time.sleep(startup_ms / 1000)
            return MeasuredAdapter(delay_ms, records, lock)

        runtime = ElasticOpportunityRuntime(
            ipc=root, host="host",
            adapters=[MeasuredAdapter(delay_ms, records, lock)],
            adapter_factory=factory, maximum_adapters=4,
            slow_offer_ms=5, shed_after_ms=50,
            kinds={"tiny.observe"}, batch_size=100, idle_ms=1,
            journal=root / "runtime.jsonl",
        )
        began = time.perf_counter_ns()
        runtime.drain(total)
        drain_ms = (time.perf_counter_ns() - began) / 1e6
        peak = max([1, *(capacity for event, capacity in runtime.capacity_events
                        if event == "GROW")])
        time.sleep(.055)
        while len(runtime.adapters) > 1:
            runtime.visit()
        result = {
            "candidates": total,
            "adapter_delay_ms": delay_ms,
            "scheduling": "elastic-1-to-4",
            "drain_ms": round(drain_ms, 3),
            "throughput_per_s": round(total / (drain_ms / 1000), 2),
            "peak_adapters": peak,
            "final_adapters_after_idle": len(runtime.adapters),
            "capacity_events": runtime.capacity_events,
            "startup_ms_per_growth": startup_ms,
            "operational_errors": len(runtime.operational_errors),
        }
        runtime.close()
        return result


def main() -> None:
    results = []
    # Keep this elastic comparison compact. The preceding scheduling experiment
    # owns the 1k/10k scale curves; this one isolates policy and startup cost.
    for total, delay in ((100, 0), (100, 10), (100, 100)):
        results.append(trial(total, delay, False, False))
        results.append(trial(total, delay, True, False))
        results.append(elastic_trial(total, delay))
    value = {"schema": "PORTER-ELASTIC-OPPORTUNITY-CAPACITY/1", "results": results}
    rendered = json.dumps(value, indent=2)
    print(rendered)
    Path("benchmarks/results/elastic-capacity.json").write_text(rendered + "\n")


if __name__ == "__main__":
    main()
