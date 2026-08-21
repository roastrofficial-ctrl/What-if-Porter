#!/usr/bin/env python3
from __future__ import annotations

import json
import statistics
import tempfile
import threading
import time
from pathlib import Path

from opportunity_scheduling import MeasuredAdapter, populate
from porter.opportunities import ElasticOpportunityRuntime


class SynchronousAcquisitionRuntime(ElasticOpportunityRuntime):
    """Superseded elastic acquisition retained as the control."""
    def _grow(self):
        if len(self.adapters) >= self.maximum_adapters:
            return
        adapter = self.adapter_factory()
        self.adapters.append(adapter)
        self.available.put(adapter)
        self.available_count += 1
        self.capacity_events.append(("GROW", len(self.adapters)))
        self.last_capacity_change_at = time.monotonic()


def trial(total, delay_ms, asynchronous):
    with tempfile.TemporaryDirectory(prefix="porter-acquisition-") as folder:
        root=Path(folder);populate(root,total)
        records=[];lock=threading.Lock()
        def create():
            time.sleep(.045)
            return MeasuredAdapter(delay_ms,records,lock)
        cls=ElasticOpportunityRuntime if asynchronous else SynchronousAcquisitionRuntime
        runtime=cls(
            ipc=root,host="host",adapters=[MeasuredAdapter(delay_ms,records,lock)],
            adapter_factory=create,maximum_adapters=4,slow_offer_ms=5,
            shed_after_ms=1000,evidence_window=8,inspection_interval_ms=10,
            kinds={"tiny.observe"},batch_size=100,idle_ms=1,
            journal=root/"runtime.jsonl")
        visits=[];began=time.perf_counter_ns();began_wall=time.time_ns()
        maximum_committed=0
        while runtime.control_returns<total:
            visit_began=time.perf_counter_ns();runtime.visit()
            visits.append((time.perf_counter_ns()-visit_began)/1e6)
            maximum_committed=max(maximum_committed,
                len(runtime.inflight)+runtime.publication_in_progress+len(runtime.starting))
            if runtime.control_returns<total:time.sleep(.001)
        elapsed=(time.perf_counter_ns()-began)/1e6
        ordered=sorted(records,key=lambda value:value["returned_ns"])
        result={
            "candidates":total,"adapter_delay_ms":delay_ms,
            "acquisition":"asynchronous" if asynchronous else "synchronous",
            "drain_ms":round(elapsed,3),
            "first_control_ms":round((ordered[0]["returned_ns"]-began_wall)/1e6,3),
            "maximum_visit_ms":round(max(visits),3),
            "visit_p99_ms":round(sorted(visits)[max(0,int(len(visits)*.99)-1)],3),
            "peak_adapters":max([1,*(n for event,n in runtime.capacity_events if event=="GROW")]),
            "maximum_committed_opportunities":maximum_committed,
            "startup_median_ms":round(statistics.median(runtime.startup_ms),3) if runtime.startup_ms else None,
            "errors":len(runtime.operational_errors),
        }
        runtime.close();return result


def acquisition_probe(asynchronous):
    with tempfile.TemporaryDirectory(prefix="porter-acquisition-probe-") as folder:
        root=Path(folder);populate(root,0)
        records=[];lock=threading.Lock()
        def create():
            time.sleep(.045)
            return MeasuredAdapter(0,records,lock)
        cls=ElasticOpportunityRuntime if asynchronous else SynchronousAcquisitionRuntime
        runtime=cls(
            ipc=root,host="host",adapters=[MeasuredAdapter(0,records,lock)],
            adapter_factory=create,maximum_adapters=2,
            kinds={"tiny.observe"},batch_size=10,idle_ms=1,
            journal=root/"runtime.jsonl")
        began=time.perf_counter_ns();runtime._grow()
        call_ms=(time.perf_counter_ns()-began)/1e6
        while runtime.starting and not all(f.done() for f in runtime.starting):time.sleep(.001)
        runtime._reap_starting();runtime.close()
        return {"shape":"one-45ms-capacity-acquisition",
                "acquisition":"asynchronous" if asynchronous else "synchronous",
                "attention_call_ms":round(call_ms,3)}


def main():
    results=[acquisition_probe(False),acquisition_probe(True)]
    for total,delay in ((100,10),(100,100),(20,1000)):
        results.append(trial(total,delay,False));results.append(trial(total,delay,True))
    value={"schema":"PORTER-NONBLOCKING-CAPACITY-ACQUISITION/1","results":results}
    rendered=json.dumps(value,indent=2);print(rendered)
    Path("benchmarks/results/nonblocking-acquisition.json").write_text(rendered+"\n")


if __name__=="__main__":main()
