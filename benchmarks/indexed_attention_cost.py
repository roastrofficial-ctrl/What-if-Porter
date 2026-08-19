#!/usr/bin/env python3
from __future__ import annotations

import json
import statistics
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

from porter.candidates import path_for, rebuild
from porter.custody import collect_package
from porter.daemon import Porter
from porter.protocol import package


def median(values):
    return round(statistics.median(values), 3)


def transitions(indexed: bool, count: int = 100) -> dict:
    with tempfile.TemporaryDirectory(prefix="porter-transition-") as folder:
        root = Path(folder)
        porter = Porter("host", root, {})
        values = [package("sender", "host", "demo.work", {"n": n}) for n in range(count)]
        accepts = []
        collections = []
        publish_patch = patch("porter.carriage.publish", lambda *_: None) if not indexed else None
        settle_patch = patch("porter.custody.settle", lambda *_: None) if not indexed else None
        if publish_patch:
            publish_patch.start()
            settle_patch.start()
        try:
            for value in values:
                began = time.perf_counter_ns()
                porter.deposit(value)
                accepts.append((time.perf_counter_ns() - began) / 1e6)
            for value in values:
                began = time.perf_counter_ns()
                collect_package(root, value["package"], "host")
                collections.append((time.perf_counter_ns() - began) / 1e6)
        finally:
            if publish_patch:
                publish_patch.stop()
                settle_patch.stop()
        candidate = path_for(root)
        return {
            "indexed": indexed,
            "accept_median_ms": median(accepts),
            "collection_median_ms": median(collections),
            "candidate_bytes_after_settlement": candidate.stat().st_size if candidate.exists() else 0,
            "candidate_inodes": len(list((root / "candidates").iterdir())),
        }


def reconstruction(count: int) -> dict:
    with tempfile.TemporaryDirectory(prefix="porter-rebuild-") as folder:
        root = Path(folder)
        acceptances = root / "acceptances"
        acceptances.mkdir(parents=True)
        for number in range(count):
            package_id = f"PKG-{number:032x}"
            value = {
                "kind": "ACCEPTANCE",
                "acceptance": f"AC-{number:032x}",
                "recipient": "host",
                "package": {"package": package_id, "kind": "demo.work"},
            }
            (acceptances / f"{package_id}.json").write_text(json.dumps(value, separators=(",", ":")))
        began = time.perf_counter_ns()
        result = rebuild(root)
        elapsed = (time.perf_counter_ns() - began) / 1e6
        return {"candidates": count, "rebuild_ms": round(elapsed, 3), "projection_bytes": result["bytes"], "projection_inodes": len(list((root / "candidates").iterdir()))}


if __name__ == "__main__":
    print(json.dumps({
        "transitions": [transitions(False), transitions(True)],
        "reconstruction": [reconstruction(1000), reconstruction(10000)],
    }, indent=2))
