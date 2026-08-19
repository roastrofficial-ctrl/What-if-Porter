#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import resource
import statistics
import tempfile
import time
from pathlib import Path

from porter.host_runtime import HostRuntime
from porter.candidates import rebuild


class NoAdapter:
    def close(self):
        pass


def populate(root: Path, total: int) -> None:
    inbox = root / "inbox"
    acceptances = root / "acceptances"
    inbox.mkdir(parents=True)
    acceptances.mkdir(parents=True)
    for number in range(total):
        package_id = f"PKG-{number:032x}"
        package = {
            "protocol": "PORTER/1",
            "package": package_id,
            "from": "sender",
            "to": "host",
            "kind": (
                "interesting.1" if number == 0 else
                "interesting.9" if number < 10 else
                "interesting.90" if number < 100 else
                "interesting.900" if number < 1000 else
                "irrelevant"
            ),
            "created": 1,
            "expires": 4102444800,
            "payload": {"padding": "x" * 64},
        }
        (inbox / f"{package_id}.json").write_text(json.dumps(package, separators=(",", ":")))
        acceptance = {"kind": "ACCEPTANCE", "acceptance": f"AC-{number:032x}", "recipient": "host", "package": package}
        (acceptances / f"{package_id}.json").write_text(json.dumps(acceptance, separators=(",", ":")))


def scan(root: Path, kinds: set[str]) -> list[str]:
    values = []
    for path in (root / "inbox").glob("PKG-*.json"):
        package = json.loads(path.read_text())
        if not kinds or package["kind"] in kinds:
            values.append(package["package"])
    return sorted(values)


def sample(root: Path, kinds: set[str], repeats: int, mechanism: str) -> dict:
    runtime = HostRuntime(
        root, "host", NoAdapter(), kinds, 10_000, 100,
        root / "runtime.jsonl",
    )
    runtime.recovering = False
    values = []
    discovered = 0
    for _ in range(repeats):
        began = time.perf_counter_ns()
        candidates = scan(root, kinds) if mechanism == "current-scan" else runtime.candidates()
        values.append((time.perf_counter_ns() - began) / 1e6)
        discovered = len(candidates)
    return {
        "discovered": discovered,
        "median_ms": statistics.median(values),
        "p95_ms": sorted(values)[max(0, int(len(values) * 0.95) - 1)],
        "minimum_ms": min(values),
        "maximum_ms": max(values),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeats", type=int, default=15)
    parser.add_argument("--output")
    parser.add_argument("--mechanism", choices=("current-scan", "indexed"), default="indexed")
    args = parser.parse_args()
    results = []
    scenarios = (
        (0, ((0, set()),)),
        (10, ((0, {"absent"}), (1, {"interesting.1"}))),
        (1000, ((0, {"absent"}), (1, {"interesting.1"}))),
        (10000, (
            (0, {"absent"}),
            (1, {"interesting.1"}),
            (10, {"interesting.1", "interesting.9"}),
            (100, {"interesting.1", "interesting.9", "interesting.90"}),
            (1000, {"interesting.1", "interesting.9", "interesting.90", "interesting.900"}),
        )),
    )
    for total, selections in scenarios:
        with tempfile.TemporaryDirectory(prefix="porter-attention-") as folder:
            root = Path(folder)
            populate(root, total)
            if args.mechanism == "indexed":
                rebuild(root)
            inbox_bytes = sum(path.stat().st_size for path in (root / "inbox").glob("*"))
            for relevant, kinds in selections:
                result = sample(root, kinds, args.repeats, args.mechanism)
                result.update({
                    "total": total,
                    "relevant": relevant,
                    "inbox_bytes": inbox_bytes,
                    "rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                })
                results.append(result)
    value = {"mechanism": args.mechanism, "repeats": args.repeats, "results": results}
    rendered = json.dumps(value, indent=2)
    print(rendered)
    if args.output:
        Path(args.output).write_text(rendered + "\n")


if __name__ == "__main__":
    main()
