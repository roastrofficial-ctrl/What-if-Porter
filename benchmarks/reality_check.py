#!/usr/bin/env python3
from __future__ import annotations

import argparse
import contextlib
import io
import json
import math
import os
import resource
import shutil
import statistics
import tempfile
import threading
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from porter.custody import collect_package, recover_collections
from porter.daemon import Porter
from porter.lodgement import recover
from porter.protocol import package
from porter.rounds import make_round
from porter.tickets import collect, lodge


@contextlib.contextmanager
def count_filesystem_operations():
    """Count calls made by a suite without changing PORTER's implementation."""
    counts = {"opens_read": 0, "opens_write": 0, "fsync": 0, "replace": 0, "rename": 0, "unlink": 0}
    originals = {name: getattr(os, name) for name in ("fsync", "replace", "rename", "unlink")}
    original_open = io.open
    def counted_open(*args, **kwargs):
        mode = kwargs.get("mode", args[1] if len(args) > 1 else "r")
        counts["opens_write" if any(flag in mode for flag in "wax+") else "opens_read"] += 1
        return original_open(*args, **kwargs)
    def wrapper(name):
        def counted(*args, **kwargs):
            counts[name] += 1
            return originals[name](*args, **kwargs)
        return counted
    io.open = counted_open
    for name in originals: setattr(os, name, wrapper(name))
    try: yield counts
    finally:
        io.open = original_open
        for name, operation in originals.items(): setattr(os, name, operation)


def ns(): return time.perf_counter_ns()


def percentiles(values):
    ordered = sorted(values)
    def at(q): return ordered[min(len(ordered) - 1, math.ceil(q * len(ordered)) - 1)] / 1_000_000
    return {"samples": len(values), "median_ms": at(.5), "p95_ms": at(.95), "p99_ms": at(.99)}


def filesystem(root: Path):
    files = [path for path in root.rglob("*") if path.is_file()]
    groups = {}
    for path in files:
        relative = path.relative_to(root)
        nested = {
            "lodgements": {"lodged", "locks"},
            "tickets": {"by-package"},
            "collections": {"facts", "locks", "by-package"},
        }
        if len(relative.parts) > 1 and relative.parts[1] in nested.get(relative.parts[0], set()):
            key = "/".join(relative.parts[:2])
        else:
            key = str(relative.parts[0]) if relative.parts else "."
        item = groups.setdefault(key, {"files": 0, "bytes": 0})
        item["files"] += 1; item["bytes"] += path.stat().st_size
    return {"files": len(files), "bytes": sum(path.stat().st_size for path in files), "groups": groups}


def measured(operation):
    cpu0 = time.process_time_ns(); wall0 = ns(); result = operation()
    return result, {"wall_ms": (ns() - wall0) / 1_000_000, "cpu_ms": (time.process_time_ns() - cpu0) / 1_000_000}


def make_lodgements(root: Path, count: int):
    values = []
    for index in range(count):
        value = package("sender", "recipient", "bench.work", {"index": index}, reply_to="sender", ttl=86400)
        values.append((value, lodge(root, value)))
    return values


def bench_lodgement(samples):
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary); timings = []
        for index in range(samples):
            value = package("sender", "recipient", "bench.work", {"index": index}, reply_to="sender", ttl=86400)
            start = ns(); lodge(root, value); timings.append(ns() - start)
        return {"latency": percentiles(timings), "resources": filesystem(root)}


def bench_carriage(samples):
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary); origin, recipient_root = root / "origin", root / "recipient"
        recipient = Porter("recipient", recipient_root, {}); remote = []; total = []
        def transport(value, _route):
            start = ns(); evidence = recipient.deposit(value); remote.append(ns() - start); return evidence
        sender = Porter("sender", origin, {"recipient": "local"}, transport=transport)
        values = make_lodgements(origin, samples)
        for value, _ticket in values:
            start = ns(); sender.carry_one(origin / "outgoing" / f"{value['package']}.json"); total.append(ns() - start)
        local = [whole - remote_part for whole, remote_part in zip(total, remote)]
        return {"total": percentiles(total), "remote_acceptance": percentiles(remote), "attempt_and_local_evidence": percentiles(local), "origin_resources": filesystem(origin), "recipient_resources": filesystem(recipient_root)}


def bench_collection(samples):
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary); porter = Porter("recipient", root, {}); ids = []
        for index in range(samples):
            value = package("sender", "recipient", "bench.work", {"index": index}, ttl=86400); porter.deposit(value); ids.append(value["package"])
        timings = []
        for package_id in ids:
            start = ns(); collect_package(root, package_id, "recipient-host"); timings.append(ns() - start)
        return {"latency": percentiles(timings), "resources": filesystem(root)}


def bench_rounds(scales):
    results = []
    for count in scales:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); tickets = make_lodgements(root, count); ids = [ticket["ticket"] for _, ticket in tickets]
            before = filesystem(root); (_round, timing) = measured(lambda: make_round(root, ids, "benchmark-host")); after = filesystem(root)
            frequent = measured(lambda: [make_round(root, ids, "benchmark-host") for _ in range(10)])[1]
            changed_porter = Porter("sender", root, {})
            changed = package("recipient", "sender", "bench.return", {"changed": True}, in_reply_to=tickets[-1][0]["package"], ttl=86400)
            changed_porter.deposit(changed)
            changed_timing = measured(lambda: make_round(root, ids, "benchmark-host"))[1]
            results.append({"tickets": count, **timing, "per_ticket_us": timing["wall_ms"] * 1000 / count, "journal_bytes": after["groups"].get("rounds", {}).get("bytes", 0), "files_written_or_grown": after["files"] - before["files"], "bytes_growth": after["bytes"] - before["bytes"], "ten_unchanged_rounds_wall_ms": frequent["wall_ms"], "one_changed_ticket_wall_ms": changed_timing["wall_ms"]})
    return results


def bench_dormancy(scales):
    results = []
    for count in scales:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); porter = Porter("recipient", root, {})
            _, timing = measured(lambda: [porter.deposit(package("sender", "recipient", "bench.dormant", {"index": index}, ttl=86400)) for index in range(count)])
            state = filesystem(root)
            results.append({"held": count, **timing, "per_package_ms": timing["wall_ms"] / count, "files": state["files"], "bytes": state["bytes"], "bytes_per_package": state["bytes"] / count, "groups": state["groups"]})
    return results


def bench_recovery(scales):
    results = []
    for count in scales:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); facts = make_lodgements(root, count)
            shutil.rmtree(root / "tickets"); shutil.rmtree(root / "outgoing")
            _, rebuild = measured(lambda: recover(root))
            _, healthy = measured(lambda: recover(root))
            results.append({"facts": count, "rebuild_wall_ms": rebuild["wall_ms"], "healthy_restart_wall_ms": healthy["wall_ms"], "rebuild_per_fact_ms": rebuild["wall_ms"] / count, "healthy_per_fact_ms": healthy["wall_ms"] / count, "resources": filesystem(root)})
    return results


def bench_concurrency(total, workers):
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary); lock = threading.Lock(); latencies = []
        def work(offset, amount):
            local = []
            for index in range(amount):
                value = package("sender", "recipient", "bench.concurrent", {"index": offset + index}, ttl=86400)
                start = ns(); lodge(root, value); local.append(ns() - start)
            with lock: latencies.extend(local)
        each, remainder = divmod(total, workers)
        amounts = [each + (1 if worker < remainder else 0) for worker in range(workers)]
        offset = 0; threads = []
        for worker, amount in enumerate(amounts):
            threads.append(threading.Thread(target=work, args=(offset, amount)))
            offset += amount
        _, timing = measured(lambda: ([thread.start() for thread in threads], [thread.join() for thread in threads]))
        return {"lodgements": total, "workers": workers, **timing, "throughput_per_second": total / (timing["wall_ms"] / 1000), "latency": percentiles(latencies), "resources": filesystem(root)}


def main():
    parser = argparse.ArgumentParser(description="PORTER 1.0 reproducible reality-check benchmark")
    parser.add_argument("--profile", default="measurement")
    parser.add_argument("--samples", type=int, default=200)
    parser.add_argument("--max-scale", type=int, default=1000, choices=(1000, 10000))
    parser.add_argument("--output")
    parser.add_argument("--quiet", action="store_true", help="write JSON without also printing it")
    parser.add_argument("--only", help="comma-separated suites: lodgement,carriage,collection,rounds,dormancy,recovery,concurrency")
    args = parser.parse_args()
    scales = [1, 10, 100, 1000] + ([10000] if args.max_scale == 10000 else [])
    started = time.time()
    report = {
        "benchmark": "PORTER 1.0 Reality Check", "profile": args.profile, "started_unix": started,
        "configuration": {"samples": args.samples, "scales": scales},
    }
    requested = set(args.only.split(",")) if args.only else {"lodgement", "carriage", "collection", "rounds", "dormancy", "recovery", "concurrency"}
    suites = {
        "lodgement": lambda: bench_lodgement(args.samples), "carriage": lambda: bench_carriage(args.samples),
        "collection": lambda: bench_collection(args.samples), "rounds": lambda: bench_rounds(scales),
        "dormancy": lambda: bench_dormancy(scales), "recovery": lambda: bench_recovery(scales),
        "concurrency": lambda: bench_concurrency(args.samples, 8),
    }
    unknown = requested - suites.keys()
    if unknown: parser.error("unknown suites: " + ", ".join(sorted(unknown)))
    report["filesystem_operations"] = {}
    for name in suites:
        if name in requested:
            with count_filesystem_operations() as operations:
                report[name] = suites[name]()
            report["filesystem_operations"][name] = operations
    report["elapsed_seconds"] = time.time() - started
    raw_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    report["process_max_rss_bytes"] = raw_rss if sys.platform == "darwin" else raw_rss * 1024
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.output: Path(args.output).write_text(rendered + "\n")
    if not args.quiet: print(rendered)


if __name__ == "__main__": main()
