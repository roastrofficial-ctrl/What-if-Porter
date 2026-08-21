#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
import threading
import time
from pathlib import Path

from opportunity_scheduling import populate
from porter.opportunities import ElasticOpportunityRuntime


class PatternAdapter:
    def __init__(self, delays, records, lock):
        self.delays, self.records, self.lock = delays, records, lock

    def dispatch(self, dispatch_id, collection):
        number = collection["package"]["payload"]["n"]
        delay = self.delays[number]
        began = time.perf_counter_ns()
        if delay:
            time.sleep(delay / 1000)
        with self.lock:
            self.records.append((number, delay, (time.perf_counter_ns() - began) / 1e6))
        return {"contract": "PORTER-HOST-ADAPTER/1", "dispatch": dispatch_id,
                "runtime_observation": "ADAPTER_RETURNED_CONTROL"}

    def close(self, grace_seconds=0):
        pass


class SingleSampleElasticRuntime(ElasticOpportunityRuntime):
    """The superseded policy retained only as a pressure control."""
    def _slow_evidence(self):
        recent_slow = bool(self.offer_ms and self.offer_ms[-1] >= self.slow_offer_ms)
        active_slow = super()._slow_evidence() > sum(
            value >= self.slow_offer_ms for value in self.offer_ms[-self.evidence_window:]
        )
        return len(self.adapters) if recent_slow or active_slow else 0

    def _cheap_window(self):
        return False


def trial(name, delays, stable):
    with tempfile.TemporaryDirectory(prefix="porter-mixed-") as folder:
        root = Path(folder); populate(root, len(delays))
        records, lock = [], threading.Lock()
        def create():
            time.sleep(.045)
            return PatternAdapter(delays, records, lock)
        cls = ElasticOpportunityRuntime if stable else SingleSampleElasticRuntime
        runtime = cls(
            ipc=root, host="host", adapters=[PatternAdapter(delays, records, lock)],
            adapter_factory=create, maximum_adapters=4, slow_offer_ms=5,
            shed_after_ms=50, evidence_window=8,
            minimum_capacity_residence_ms=50,
            kinds={"tiny.observe"}, batch_size=100, idle_ms=1,
            journal=root / "runtime.jsonl",
        )
        began = time.perf_counter_ns()
        runtime.drain(len(delays))
        drain_ms = (time.perf_counter_ns() - began) / 1e6
        time.sleep(.055)
        while len(runtime.adapters) > 1:
            runtime.visit()
        result = {
            "workload": name,
            "policy": "windowed-hysteresis" if stable else "single-sample",
            "items": len(delays), "drain_ms": round(drain_ms, 3),
            "peak_adapters": max([1, *(n for event, n in runtime.capacity_events
                                        if event == "GROW")]),
            "growths": sum(event == "GROW" for event, _ in runtime.capacity_events),
            "sheds": sum(event == "SHED" for event, _ in runtime.capacity_events),
            "final_adapters": len(runtime.adapters),
            "capacity_events": runtime.capacity_events,
            "errors": len(runtime.operational_errors),
        }
        runtime.close()
        return result


def main():
    workloads = {
        "isolated-slow": [30] + [0] * 59,
        "alternating": [30 if n % 2 else 0 for n in range(60)],
        "clustered": [0] * 15 + [30] * 20 + [0] * 25,
        "sustained-slow": [30] * 60,
    }
    results = []
    for name, delays in workloads.items():
        results.append(trial(name, delays, False))
        results.append(trial(name, delays, True))
    value = {"schema": "PORTER-ELASTIC-MIXED-LATENCY/1", "results": results}
    rendered = json.dumps(value, indent=2)
    print(rendered)
    Path("benchmarks/results/mixed-latency.json").write_text(rendered + "\n")


if __name__ == "__main__":
    main()
