#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
import threading
import time
from pathlib import Path

from opportunity_scheduling import MeasuredAdapter, populate
from porter.opportunities import ElasticOpportunityRuntime


class EagerInspectionRuntime(ElasticOpportunityRuntime):
    """Superseded loop retained as the experimental control."""
    def visit(self):
        self.candidate_snapshot = []
        self.last_inspection_at = float("-inf")
        self._refresh_snapshot()
        return super().visit()


class GateAdapter(MeasuredAdapter):
    def __init__(self, gate):
        super().__init__()
        self.gate = gate

    def dispatch(self, dispatch_id, collection):
        self.gate.wait()
        return super().dispatch(dispatch_id, collection)

    def close(self, grace_seconds=0):
        self.gate.set()


def runtime(cls, root, adapters, factory, maximum, interval=50):
    return cls(
        ipc=root, host="host", adapters=adapters, adapter_factory=factory,
        maximum_adapters=maximum, slow_offer_ms=5, shed_after_ms=50,
        inspection_interval_ms=interval, kinds={"tiny.observe"},
        batch_size=100, idle_ms=1, journal=root / "runtime.jsonl",
    )


def full_capacity_trial(eager):
    with tempfile.TemporaryDirectory(prefix="porter-inspection-full-") as folder:
        root = Path(folder); populate(root, 1000)
        gate = threading.Event(); cls = EagerInspectionRuntime if eager else ElasticOpportunityRuntime
        value = runtime(cls, root, [GateAdapter(gate)], lambda: GateAdapter(gate), 1)
        value.visit()
        deadline = time.monotonic() + 2
        while not value.inflight and time.monotonic() < deadline:
            time.sleep(.001)
        began = time.perf_counter_ns()
        for _ in range(100):
            value.visit()
        probe_ms = (time.perf_counter_ns() - began) / 1e6
        result = {"shape":"full-capacity-100-reaps",
                  "policy":"eager" if eager else "snapshot",
                  "probe_ms":round(probe_ms,3),
                  "inspections":value.inspection_count,
                  "inspection_ms":round(value.inspection_ms,3)}
        gate.set(); value.drain(1); value.close()
        return result


def drain_trial(eager):
    with tempfile.TemporaryDirectory(prefix="porter-inspection-drain-") as folder:
        root = Path(folder); populate(root, 200)
        records, lock = [], threading.Lock()
        create = lambda: MeasuredAdapter(10, records, lock)
        cls = EagerInspectionRuntime if eager else ElasticOpportunityRuntime
        value = runtime(cls, root, [create()], create, 4, interval=10)
        began = time.perf_counter_ns(); value.drain(200)
        drain_ms = (time.perf_counter_ns() - began) / 1e6
        result = {"shape":"200-candidates-10ms",
                  "policy":"eager" if eager else "snapshot",
                  "drain_ms":round(drain_ms,3),
                  "inspections":value.inspection_count,
                  "inspection_ms":round(value.inspection_ms,3),
                  "peak_adapters":value.maximum_inflight,
                  "returns":value.control_returns}
        value.close(); return result


def main():
    results = [full_capacity_trial(True), full_capacity_trial(False),
               drain_trial(True), drain_trial(False)]
    value = {"schema":"PORTER-ATTENTION-INSPECTION-DECOUPLING/1",
             "results":results}
    rendered=json.dumps(value,indent=2); print(rendered)
    Path("benchmarks/results/inspection-decoupling.json").write_text(rendered+"\n")


if __name__ == "__main__":
    main()
