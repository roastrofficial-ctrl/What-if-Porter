#!/usr/bin/env python3
from __future__ import annotations

import json
import statistics
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import patch

from opportunity_scheduling import MeasuredAdapter, populate
from porter.opportunities import BoundedOpportunityRuntime
import porter.opportunities as opportunity_module


def trial(total, delay_ms, mode):
    with tempfile.TemporaryDirectory(prefix="porter-phases-") as folder:
        root=Path(folder); populate(root,total)
        records=[]; record_lock=threading.Lock()
        count=1 if mode=="serial" else 4
        adapters=[MeasuredAdapter(delay_ms,records,record_lock) for _ in range(count)]
        active=0; maximum_publications=0; publication_ms=[]; lock=threading.Lock()
        original=opportunity_module.collect_package
        def measured(*args,**kwargs):
            nonlocal active,maximum_publications
            with lock:
                active+=1; maximum_publications=max(maximum_publications,active)
            began=time.perf_counter_ns()
            try:
                return original(*args,**kwargs)
            finally:
                elapsed=(time.perf_counter_ns()-began)/1e6
                with lock:
                    publication_ms.append(elapsed); active-=1
        runtime=BoundedOpportunityRuntime(
            ipc=root,host="host",adapters=adapters,max_inflight_offers=count,
            serial_publication=mode!="parallel-publication",
            kinds={"tiny.observe"},batch_size=100,idle_ms=1,
            journal=root/"runtime.jsonl")
        cpu_began=time.process_time_ns(); began=time.perf_counter_ns()
        with patch("porter.opportunities.collect_package",measured):
            runtime.drain(total)
        elapsed=(time.perf_counter_ns()-began)/1e6
        cpu_ms=(time.process_time_ns()-cpu_began)/1e6
        result={
            "candidates":total,"adapter_delay_ms":delay_ms,"mode":mode,
            "drain_ms":round(elapsed,3),"cpu_ms":round(cpu_ms,3),
            "throughput_per_s":round(total/(elapsed/1000),2),
            "maximum_publications":maximum_publications,
            "maximum_adapter_waits":runtime.maximum_inflight,
            "publication_median_ms":round(statistics.median(publication_ms),3),
            "publication_p99_ms":round(sorted(publication_ms)[max(0,int(len(publication_ms)*.99)-1)],3),
            "cl_to_offer_median_ms":round(statistics.median(x["cl_to_offer_ms"] for x in records),3),
            "errors":len(runtime.operational_errors),
        }
        runtime.close(); return result


def main():
    results=[]
    for total,delay in ((200,0),(500,0),(200,10),(100,100)):
        for mode in ("serial","parallel-publication","serial-publication-parallel-wait"):
            results.append(trial(total,delay,mode))
    value={"schema":"PORTER-PUBLICATION-WAIT-PHASE-SEPARATION/1","results":results}
    rendered=json.dumps(value,indent=2);print(rendered)
    Path("benchmarks/results/phase-separation.json").write_text(rendered+"\n")


if __name__=="__main__":main()
