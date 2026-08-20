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
from porter.history import enumerate_candidate_facts


def populate(root: Path, total: int, collected: int = 0) -> None:
    acceptances = root / "acceptances"
    associations = root / "collections" / "by-package"
    acceptances.mkdir(parents=True)
    associations.mkdir(parents=True)
    for number in range(total):
        package_id = f"PKG-{number:032x}"
        package = {
            "protocol": "PORTER/1", "package": package_id, "from": "sender",
            "to": "host", "kind": "demo.work", "created": 1,
            "expires": 4102444800, "payload": {"padding": "x" * 64},
        }
        acceptance = {
            "protocol": "PORTER/1", "kind": "REMOTE_ACCEPTANCE",
            "acceptance": f"AC-{number:032x}", "recipient": "host",
            "package": package, "package_digest": f"sha256:{number:064x}",
            "accepted_at_ms": number,
        }
        (acceptances / f"{package_id}.json").write_text(
            json.dumps(acceptance, separators=(",", ":"))
        )
        if number < collected:
            (associations / package_id).write_text(f"CL-{number:032x}\n")


def legacy(root: Path):
    began = time.perf_counter_ns()
    cpu_began = time.process_time_ns()
    collected = root / "collections" / "by-package"
    collected_ids = {path.name for path in collected.glob("PKG-*")}
    values = []
    bytes_read = 0
    paths = sorted((root / "acceptances").glob("PKG-*.json"))
    for path in paths:
        encoded = path.read_bytes()
        bytes_read += len(encoded)
        value = json.loads(encoded)
        package = value["package"]
        if package["package"] not in collected_ids:
            values.append((package["package"], package["kind"]))
    elapsed = time.perf_counter_ns() - began
    cpu = time.process_time_ns() - cpu_began
    return values, {
        "wall_ms": elapsed / 1e6, "cpu_ms": cpu / 1e6,
        "filesystem_wait_estimate_ms": max(0, elapsed - cpu) / 1e6,
        "directories_visited": 2, "files_opened": len(paths),
        "bytes_read": bytes_read, "path_stat_operations": 0,
        "json_decodes": len(paths), "cl_association_lookups": len(paths),
    }


def summarize(samples):
    ordered = sorted(samples, key=lambda value: value["wall_ms"])
    walls = [value["wall_ms"] for value in ordered]
    return {
        "median_wall_ms": round(statistics.median(walls), 3),
        "minimum_wall_ms": round(min(walls), 3),
        "maximum_wall_ms": round(max(walls), 3),
        "representative": ordered[len(ordered) // 2],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sizes", default="100,1000,10000")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--output")
    parser.add_argument("--include-legacy-10000", action="store_true")
    args = parser.parse_args()
    results = []
    for total in [int(value) for value in args.sizes.split(",")]:
        with tempfile.TemporaryDirectory(prefix="porter-history-") as folder:
            root = Path(folder)
            populate(root, total, total // 10)
            canonical_bytes = sum(entry.stat().st_size for entry in os.scandir(root / "acceptances"))
            strategies = [("canonical-scandir", lambda: enumerate_candidate_facts(root, measured=True))]
            if total < 10000 or args.include_legacy_10000:
                strategies.insert(0, ("independent-file-legacy", lambda: legacy(root)))
            for strategy, operation in strategies:
                samples = []
                candidates = 0
                for _ in range(args.repeats):
                    values, metrics = operation()
                    candidates = len(values)
                    samples.append(metrics)
                results.append({
                    "facts": total, "collected": total // 10,
                    "candidates": candidates, "strategy": strategy,
                    "canonical_bytes": canonical_bytes,
                    "physical_fixture_inodes": total + total // 10,
                    "canonical_ac_inodes": total,
                    "cl_association_projection_inodes": total // 10,
                    **summarize(samples),
                })
            began = time.perf_counter_ns()
            rebuilt = rebuild(root)
            results.append({
                "facts": total, "strategy": "candidate-reconstruction",
                "wall_ms": round((time.perf_counter_ns() - began) / 1e6, 3),
                **rebuilt,
            })
    output = {
        "schema": "PORTER-CANONICAL-HISTORY-ENUMERATION/1",
        "repeats": args.repeats,
        "rss_kib": round(
            resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 if sys.platform == "darwin" else 1)
        ),
        "results": results,
    }
    rendered = json.dumps(output, indent=2)
    print(rendered)
    if args.output:
        Path(args.output).write_text(rendered + "\n")


if __name__ == "__main__":
    main()
