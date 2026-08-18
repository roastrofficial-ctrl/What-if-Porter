#!/usr/bin/env python3
from __future__ import annotations

import base64
import json
import os
import resource
import statistics
import tempfile
import time
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

from porter.native import public_key
from porter.rendezvous import (
    RendezvousKnowledge,
    continuity_public_key,
    sign_transition,
)


def encoded_private(key):
    return base64.b64encode(
        key.private_bytes(
            serialization.Encoding.Raw,
            serialization.PrivateFormat.Raw,
            serialization.NoEncryption(),
        )
    ).decode()


def percentile(values, amount):
    return sorted(values)[min(len(values) - 1, int(len(values) * amount))]


def snapshot(root):
    files = [path for path in root.rglob("*") if path.is_file()]
    return {"files": len(files), "bytes": sum(path.stat().st_size for path in files)}


def main():
    continuity_private = encoded_private(Ed25519PrivateKey.generate())
    continuity_public = continuity_public_key(continuity_private)
    old_private = encoded_private(X25519PrivateKey.generate())
    new_private = encoded_private(X25519PrivateKey.generate())
    configured = {
        "harmonicdb": {
            "host": "carrier-a",
            "port": 7411,
            "public_key": public_key(old_private),
        }
    }
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        knowledge = RendezvousKnowledge(
            root, configured, {"harmonicdb": continuity_public}
        )
        current = knowledge.status("harmonicdb")

        static = []
        known = []
        for _ in range(10_000):
            started = time.perf_counter_ns()
            _ = configured["harmonicdb"]
            static.append(time.perf_counter_ns() - started)
            started = time.perf_counter_ns()
            _ = knowledge.route("harmonicdb")
            known.append(time.perf_counter_ns() - started)

        started = time.perf_counter_ns()
        claim = sign_transition(
            continuity_private,
            "harmonicdb",
            1,
            current["rendezvous"],
            {"host": "weird-new-container-thing", "port": 9177},
            public_key(new_private),
        )
        creation_ns = time.perf_counter_ns() - started
        started = time.perf_counter_ns()
        knowledge.accept(claim)
        acceptance_ns = time.perf_counter_ns() - started

        before = snapshot(root)
        invalid_signature = dict(claim)
        invalid_signature["signature"] = "ed25519:" + base64.b64encode(b"x" * 64).decode()
        substituted = json.loads(json.dumps(claim))
        substituted["location"]["port"] = 1
        oversized = {**claim, "padding": "x" * 20_000}
        unknown = {**claim, "porter": "random-attacker"}
        old_replay = claim
        cases = [invalid_signature, substituted, oversized, unknown, old_replay]
        rejected = 0
        started_wall = time.perf_counter_ns()
        started_cpu = time.process_time_ns()
        for index in range(10_000):
            try:
                knowledge.accept(cases[index % len(cases)])
            except Exception:
                rejected += 1
        hostile_cpu_ns = time.process_time_ns() - started_cpu
        hostile_wall_ns = time.perf_counter_ns() - started_wall
        after = snapshot(root)

        result = {
            "environment": "single-process local filesystem",
            "ordinary_lookup_ns": {
                "static_median": int(statistics.median(static)),
                "authenticated_knowledge_median": int(statistics.median(known)),
                "authenticated_knowledge_p95": int(percentile(known, 0.95)),
            },
            "movement_ns": {
                "evidence_creation": creation_ns,
                "local_verification_and_threshold": acceptance_ns,
            },
            "hostile_10000": {
                "rejected": rejected,
                "authentic_replays": 10_000 - rejected,
                "wall_ns": hostile_wall_ns,
                "cpu_ns": hostile_cpu_ns,
                "files_created": after["files"] - before["files"],
                "bytes_growth": after["bytes"] - before["bytes"],
                "max_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                * 1024,
            },
            "claim_bytes": len(json.dumps(claim, separators=(",", ":")).encode()),
        }
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
