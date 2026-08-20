from __future__ import annotations

import json
import os
import time
from pathlib import Path


def _entries(folder: Path, prefix: str, suffix: str) -> tuple[list[os.DirEntry], int]:
    """Discover a bounded fact family with one directory enumeration.

    Path.glob/Path.exists are convenient but turn a large canonical scan into
    repeated Python/pathlib filesystem ceremonies.  scandir returns the names
    already supplied by the directory enumeration and does not stat each fact.
    """
    try:
        entries = [
            entry
            for entry in os.scandir(folder)
            if entry.name.startswith(prefix) and entry.name.endswith(suffix)
        ]
    except FileNotFoundError:
        return [], 0
    entries.sort(key=lambda entry: entry.name)
    return entries, 1


def enumerate_candidate_facts(root: Path, measured: bool = False):
    """Return AC minus CL without introducing another source of truth.

    Both existence sets and every candidate value come directly from canonical
    objects.  No catalogue, cursor, manifest, or candidate row is consulted.
    When ``measured`` is true, return operation counts and phase timings too.
    """
    wall_started = time.perf_counter_ns()
    cpu_started = time.process_time_ns()
    metrics = {
        "directories_visited": 0,
        "files_opened": 0,
        "bytes_read": 0,
        "path_stat_operations": 0,
        "json_decodes": 0,
        "fact_validations": 0,
        "package_ac_relationship_lookups": 0,
        "cl_association_lookups": 0,
        "lock_operations": 0,
    }
    timings = {
        "directory_enumeration_ms": 0.0,
        "fact_path_discovery_ms": 0.0,
        "open_ms": 0.0,
        "read_ms": 0.0,
        "json_decode_ms": 0.0,
        "fact_validation_ms": 0.0,
        "package_ac_relationship_lookup_ms": 0.0,
        "cl_association_lookup_ms": 0.0,
    }

    began = time.perf_counter_ns()
    collection_entries, visited = _entries(
        root / "collections" / "by-package", "PKG-", ""
    )
    metrics["directories_visited"] += visited
    acceptance_entries, visited = _entries(root / "acceptances", "PKG-", ".json")
    metrics["directories_visited"] += visited
    timings["directory_enumeration_ms"] = (time.perf_counter_ns() - began) / 1e6

    began = time.perf_counter_ns()
    collected_ids = {entry.name for entry in collection_entries}
    timings["fact_path_discovery_ms"] = (time.perf_counter_ns() - began) / 1e6

    values = []
    for entry in acceptance_entries:
        began = time.perf_counter_ns()
        descriptor = os.open(entry.path, os.O_RDONLY)
        timings["open_ms"] += (time.perf_counter_ns() - began) / 1e6
        metrics["files_opened"] += 1
        try:
            began = time.perf_counter_ns()
            chunks = []
            while True:
                chunk = os.read(descriptor, 65536)
                if not chunk:
                    break
                chunks.append(chunk)
                metrics["bytes_read"] += len(chunk)
            encoded = b"".join(chunks)
            timings["read_ms"] += (time.perf_counter_ns() - began) / 1e6
        finally:
            os.close(descriptor)

        began = time.perf_counter_ns()
        value = json.loads(encoded)
        timings["json_decode_ms"] += (time.perf_counter_ns() - began) / 1e6
        metrics["json_decodes"] += 1

        began = time.perf_counter_ns()
        if not isinstance(value, dict) or not isinstance(value.get("package"), dict):
            raise ValueError(f"malformed canonical acceptance {entry.name}")
        package = value["package"]
        if not isinstance(package.get("package"), str) or not isinstance(package.get("kind"), str):
            raise ValueError(f"malformed canonical acceptance {entry.name}")
        timings["fact_validation_ms"] += (time.perf_counter_ns() - began) / 1e6
        metrics["fact_validations"] += 1

        began = time.perf_counter_ns()
        package_id, kind = package["package"], package["kind"]
        timings["package_ac_relationship_lookup_ms"] += (time.perf_counter_ns() - began) / 1e6
        metrics["package_ac_relationship_lookups"] += 1

        began = time.perf_counter_ns()
        collected = package_id in collected_ids
        timings["cl_association_lookup_ms"] += (time.perf_counter_ns() - began) / 1e6
        metrics["cl_association_lookups"] += 1
        if not collected:
            values.append((package_id, kind))

    if not measured:
        return values
    wall_finished = time.perf_counter_ns()
    cpu_finished = time.process_time_ns()
    metrics.update(timings)
    metrics.update({
        "candidates": len(values),
        "wall_ms": (wall_finished - wall_started) / 1e6,
        "cpu_ms": (cpu_finished - cpu_started) / 1e6,
        "filesystem_wait_estimate_ms": max(
            0.0,
            (wall_finished - wall_started - (cpu_finished - cpu_started)) / 1e6,
        ),
    })
    return values, metrics
