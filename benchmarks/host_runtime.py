#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import statistics
import tempfile
import threading
import time
from pathlib import Path

from porter.daemon import Porter
from porter.host_runtime import Adapter, HostRuntime
from porter.protocol import package


def payload(profile: str) -> tuple[str, dict]:
    if profile == "find-me":
        return (
            "mailweb.request",
            {
                "request": {
                    "mailweb": "0.6",
                    "id": "06G1KAM4DBFS57CJHDTAMFDVG8",
                    "method": "GET",
                    "uri": "mailweb://find-me.local/stack",
                    "headers": {},
                }
            },
        )
    return (
        "hdbe.call",
        {"operation": "info", "parameters": {}, "deposited_at_ms": int(time.time() * 1000)},
    )


def prepare(root: Path, host: str, profile: str, count: int, start: int = 0) -> list[str]:
    porter = Porter(host, root, {})
    kind, body = payload(profile)
    identities = []
    for index in range(start, start + count):
        value = package(
            "benchmark-sender",
            host,
            kind,
            {**body, "runtime_benchmark_sequence": index},
            reply_to="benchmark-sender",
            ttl=3600,
        )
        value["package"] = f"PKG-{index:032x}"
        porter.deposit(value)
        identities.append(value["package"])
    return identities


def journal_metrics(path: Path) -> dict:
    values = [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
    dispatches = [value for value in values if value["observation"] == "ADAPTER_RETURNED_CONTROL"]
    visits = [value for value in values if value["observation"] == "VISIT_ENDED"]
    return {
        "dispatch_ms": [value["dispatch_ms"] for value in dispatches],
        "visit_ms": visits[-1]["visit_ms"] if visits else 0.0,
    }


def trial(args, count: int, episodic: bool) -> dict:
    with tempfile.TemporaryDirectory(prefix=f"porter-runtime-{args.profile}-") as folder:
        root = Path(folder)
        os.environ["PORTER_IPC"] = str(root)
        os.environ["FIND_ME_WORK_DIR"] = str(root / "find-me-application")
        os.environ["HARMONIC_APPLICATION_DIR"] = str(root / "harmonic-application")
        prepare(root, args.host, args.profile, count)
        journal = root / "runtime.jsonl"
        began = time.perf_counter_ns()
        adapter = Adapter(args.adapter)
        startup_ms = adapter.startup_ms
        runtime = HostRuntime(
            ipc=root,
            host=args.host,
            adapter=adapter,
            kinds={payload(args.profile)[0]},
            batch_size=max(1, count),
            idle_ms=args.idle_ms,
            journal=journal,
        )
        ready_at = time.perf_counter_ns()
        dispatched = runtime.visit()
        work_ended = time.perf_counter_ns()
        adapter.close()
        ended = time.perf_counter_ns()
        metrics = journal_metrics(journal)
        return {
            "packages": count,
            "model": "episodic" if episodic else "warm",
            "adapter_startup_ms": round(startup_ms, 3),
            "work_ms": round((work_ended - ready_at) / 1e6, 3),
            "total_ms": round((ended - began) / 1e6, 3) if episodic else round((work_ended - ready_at) / 1e6, 3),
            "shutdown_ms": round((ended - work_ended) / 1e6, 3),
            "visit_ms": metrics["visit_ms"],
            "dispatch_median_ms": round(statistics.median(metrics["dispatch_ms"]), 3) if metrics["dispatch_ms"] else None,
            "dispatch_first_ms": metrics["dispatch_ms"][0] if metrics["dispatch_ms"] else None,
            "dispatched": dispatched,
        }


def batch_trial(args, count: int, batch_size: int, late: int = 0) -> dict:
    with tempfile.TemporaryDirectory(prefix=f"porter-pressure-{args.profile}-") as folder:
        root = Path(folder)
        os.environ["PORTER_IPC"] = str(root)
        os.environ["FIND_ME_WORK_DIR"] = str(root / "find-me-application")
        os.environ["HARMONIC_APPLICATION_DIR"] = str(root / "harmonic-application")
        initial = prepare(root, args.host, args.profile, count)
        adapter = Adapter(args.adapter)
        journal = root / "runtime.jsonl"
        runtime = HostRuntime(
            ipc=root,
            host=args.host,
            adapter=adapter,
            kinds={payload(args.profile)[0]},
            batch_size=batch_size,
            idle_ms=args.idle_ms,
            journal=journal,
        )
        producer = None
        if late:
            def arrive():
                time.sleep(0.02)
                prepare(root, args.host, args.profile, late, start=count)
            producer = threading.Thread(target=arrive)
            producer.start()
        total = count + late
        began_wall_ms = int(time.time() * 1000)
        began = time.perf_counter_ns()
        dispatched = 0
        visits = 0
        while dispatched < total:
            handled = runtime.visit()
            dispatched += handled
            visits += 1
            if handled == 0:
                time.sleep(0.005)
        if producer:
            producer.join()
        elapsed_ms = (time.perf_counter_ns() - began) / 1e6
        adapter.close()
        values = [json.loads(line) for line in journal.read_text().splitlines()]
        returned = {
            value["package"]: value["at_ms"] - began_wall_ms
            for value in values
            if value["observation"] == "ADAPTER_RETURNED_CONTROL"
        }
        newest = f"PKG-{total - 1:032x}"
        return {
            "packages": total,
            "initial_packages": count,
            "arrived_while_busy": late,
            "batch_size": batch_size,
            "visits": visits,
            "elapsed_ms": round(elapsed_ms, 3),
            "throughput_per_s": round(total / (elapsed_ms / 1000), 2),
            "oldest_latency_ms": returned[initial[0]] if initial else None,
            "newest_latency_ms": returned[newest] if total else None,
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=("find-me", "harmonicdb"), required=True)
    parser.add_argument("--host", required=True)
    parser.add_argument("--adapter", required=True)
    parser.add_argument("--idle-ms", type=int, default=100)
    parser.add_argument("--output")
    args = parser.parse_args()
    results = []
    for count in (0, 1, 10, 100):
        results.append(trial(args, count, episodic=True))
        results.append(trial(args, count, episodic=False))
    default_batch = 10 if args.profile == "find-me" else 25
    batches = [batch_trial(args, 100, size) for size in (1, 10, 25, 100)]
    backlog = batch_trial(args, 500, default_batch)
    arrival_while_busy = batch_trial(args, 10, default_batch, late=100)
    value = {
        "profile": args.profile,
        "results": results,
        "batch_matrix": batches,
        "backlog": backlog,
        "arrival_while_busy": arrival_while_busy,
    }
    rendered = json.dumps(value, indent=2)
    if args.output:
        Path(args.output).write_text(rendered + "\n")
    print(rendered)


if __name__ == "__main__":
    main()
