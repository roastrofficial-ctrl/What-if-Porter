#!/usr/bin/env python3
"""A deliberately small third Host for PORTER-HOST-ADAPTER/1 pressure.

Its meaning is application-owned: preserve a digest and reversed rendering of
an opaque payload.  Normal attention produces no Return.  A separate, later
Host execution may release recorded intentions as related or unrelated
correspondence; the Runtime neither requests nor observes that decision.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

from porter.introduction import canonical
from porter.lodgement import atomic_json
from porter.protocol import package
from porter.tickets import lodge


ipc = Path(os.getenv("PORTER_IPC", "/porter"))
state = Path(os.getenv("TINY_HOST_STATE", "/data/tiny-host"))
state.mkdir(parents=True, exist_ok=True)


def observe(collection: dict) -> None:
    received = collection["package"]
    identity = received["package"]
    path = state / f"{identity}.json"
    if not path.exists():
        payload = received.get("payload")
        atomic_json(path, {
            "application": "TINY-TRANSFORM/1",
            "package": identity,
            "collection": collection["collection"],
            "payload_digest": "sha256:" + hashlib.sha256(canonical(payload)).hexdigest(),
            "local_transformation": json.dumps(payload, sort_keys=True)[::-1],
        })
    if os.getenv("TINY_HOST_DEFER_RETURN") == "1":
        atomic_json(state / f"{identity}.pending.json", {
            "package": identity,
            "reply_to": received.get("reply_to"),
            "payload_digest": json.loads(path.read_text())["payload_digest"],
        })


def release_pending(unrelated: bool = False) -> int:
    released = 0
    recipient = os.getenv("TINY_HOST_RECIPIENT", "sender")
    for path in sorted(state.glob("PKG-*.pending.json")):
        intention = json.loads(path.read_text())
        outbound = package(
            os.getenv("TINY_HOST_IDENTITY", "tiny-host"),
            recipient,
            "tiny.notice" if unrelated else "tiny.return",
            {"observed_digest": intention["payload_digest"]},
            **({} if unrelated else {"in_reply_to": intention["package"]}),
        )
        ticket = lodge(ipc, outbound)
        atomic_json(path.with_suffix(".lodged.json"), {
            "application": "TINY-TRANSFORM/1",
            "outbound": outbound["package"],
            "lodgement": ticket["lodgement"],
            "related": not unrelated,
        })
        path.unlink()
        released += 1
    return released


def serve() -> None:
    sys.stdout.write(json.dumps({
        "contract": "PORTER-HOST-ADAPTER/1",
        "runtime_observation": "ADAPTER_READY",
    }, separators=(",", ":")) + "\n")
    sys.stdout.flush()
    for line in sys.stdin:
        dispatch = json.loads(line)
        if dispatch.get("contract") != "PORTER-HOST-ADAPTER/1":
            raise SystemExit("unsupported adapter contract")
        observe(dispatch["collection"])
        sys.stdout.write(json.dumps({
            "contract": "PORTER-HOST-ADAPTER/1",
            "dispatch": dispatch["dispatch"],
            "runtime_observation": "ADAPTER_RETURNED_CONTROL",
        }, separators=(",", ":")) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    if "--release-related" in sys.argv:
        raise SystemExit(0 if release_pending(False) >= 0 else 1)
    if "--release-unrelated" in sys.argv:
        raise SystemExit(0 if release_pending(True) >= 0 else 1)
    serve()
