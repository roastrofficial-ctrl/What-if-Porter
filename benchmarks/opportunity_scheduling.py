#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import resource
import statistics
import sys
import tempfile
import threading
import time
from pathlib import Path

from porter.candidates import rebuild
from porter.host_runtime import HostRuntime
from porter.opportunities import BoundedOpportunityRuntime


class MeasuredAdapter:
    def __init__(self, delay_ms=0, records=None, lock=None):
        self.delay_ms = delay_ms
        self.records = records if records is not None else []
        self.lock = lock or threading.Lock()

    def dispatch(self, dispatch_id, collection):
        offered = time.time_ns()
        if self.delay_ms:
            time.sleep(self.delay_ms / 1000)
        returned = time.time_ns()
        with self.lock:
            self.records.append({
                "package": collection["package"]["package"],
                "cl_to_offer_ms": max(0, offered / 1e6 - collection["collected_at_ms"]),
                "adapter_ms": (returned - offered) / 1e6,
                "returned_ns": returned,
            })
        return {"contract": "PORTER-HOST-ADAPTER/1", "dispatch": dispatch_id,
                "runtime_observation": "ADAPTER_RETURNED_CONTROL"}

    def close(self, grace_seconds=0):
        pass


def populate(root, total):
    inbox, acceptances = root / "inbox", root / "acceptances"
    inbox.mkdir(parents=True); acceptances.mkdir(parents=True)
    for number in range(total):
        package_id = f"PKG-{number:032x}"
        package = {"protocol":"PORTER/1","package":package_id,"from":"sender",
                   "to":"host","kind":"tiny.observe","created":1,
                   "expires":4102444800,"payload":{"n":number}}
        acceptance = {"protocol":"PORTER/1","kind":"REMOTE_ACCEPTANCE",
                      "acceptance":f"AC-{number:032x}","recipient":"host",
                      "package":package,"package_digest":f"sha256:{number:064x}",
                      "accepted_at_ms":number}
        (inbox / f"{package_id}.json").write_text(json.dumps(package,separators=(",",":")))
        (acceptances / f"{package_id}.json").write_text(json.dumps(acceptance,separators=(",",":")))
    rebuild(root)


def percentile(values, fraction):
    ordered = sorted(values)
    return ordered[max(0, int(len(ordered) * fraction) - 1)] if ordered else None


def trial(total, delay_ms, scheduled, scan_missing, inflight=4):
    with tempfile.TemporaryDirectory(prefix="porter-opportunity-") as folder:
        root = Path(folder); populate(root, total)
        records, lock = [], threading.Lock()
        count = inflight if scheduled else 1
        adapters = [MeasuredAdapter(delay_ms, records, lock) for _ in range(count)]
        cpu_began = time.process_time_ns(); began = time.perf_counter_ns(); began_wall = time.time_ns()
        if scheduled:
            runtime = BoundedOpportunityRuntime(
                ipc=root, host="host", adapters=adapters,
                max_inflight_offers=inflight,
                scan_missing_collections=scan_missing,
                kinds={"tiny.observe"}, batch_size=100, idle_ms=10,
                journal=root / "runtime.jsonl")
            runtime.drain(total)
            maximum = runtime.maximum_inflight
            errors = len(runtime.operational_errors)
            runtime.close()
        else:
            runtime = HostRuntime(root, "host", adapters[0], {"tiny.observe"},
                                  100, 10, root / "runtime.jsonl")
            # Legacy comparison deliberately restores the old missing-mapping
            # scan at the Collection call site without changing semantics.
            if scan_missing:
                import porter.host_runtime as module
                original = module.collect_package
                def legacy(ipc, package_id, host, scan_missing=False):
                    return original(ipc, package_id, host, scan_missing=True)
                module.collect_package = legacy
            try:
                dispatched = 0
                while dispatched < total:
                    dispatched += runtime.visit()
            finally:
                if scan_missing:
                    module.collect_package = original
            maximum, errors = 1 if total else 0, 0
        ended = time.perf_counter_ns(); cpu_ended = time.process_time_ns()
        ordered = sorted(records, key=lambda value: value["returned_ns"])
        return {
            "candidates": total, "adapter_delay_ms": delay_ms,
            "scheduling": "bounded-4" if scheduled else "serial",
            "collection": "legacy-scan" if scan_missing else "direct-association",
            "drain_ms": round((ended-began)/1e6,3),
            "cpu_ms": round((cpu_ended-cpu_began)/1e6,3),
            "throughput_per_s": round(total/((ended-began)/1e9),2) if total else None,
            "first_control_ms": round((ordered[0]["returned_ns"]-began_wall)/1e6,3) if ordered else None,
            "last_control_ms": round((ordered[-1]["returned_ns"]-began_wall)/1e6,3) if ordered else None,
            "cl_to_offer_median_ms": round(statistics.median(v["cl_to_offer_ms"] for v in records),3) if records else None,
            "cl_to_offer_p99_ms": round(percentile([v["cl_to_offer_ms"] for v in records],.99),3) if records else None,
            "maximum_inflight": maximum, "operational_errors": errors,
            "rss_kib": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/(1024 if sys.platform=="darwin" else 1)),
        }


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--output");parser.add_argument("--include-10000",action="store_true");args=parser.parse_args()
    results=[]
    for total in (100,1000):
        for legacy in (True,False):
            results.append(trial(total,0,False,legacy))
            results.append(trial(total,0,True,legacy))
    if args.include_10000:
        results.append(trial(10000,0,False,False))
        results.append(trial(10000,0,True,False))
    for total in ((100,1000,10000) if args.include_10000 else (100,1000)):
        for delay in ((10,) if total == 10000 else (10,100)):
            results.append(trial(total,delay,False,False))
            results.append(trial(total,delay,True,False))
    for delay in (1000,):
        results.append(trial(10,delay,False,False));results.append(trial(10,delay,True,False))
    value={"schema":"PORTER-OPPORTUNITY-SCHEDULING-PRESSURE/1","results":results};rendered=json.dumps(value,indent=2);print(rendered)
    if args.output:Path(args.output).write_text(rendered+"\n")
if __name__=="__main__":main()
