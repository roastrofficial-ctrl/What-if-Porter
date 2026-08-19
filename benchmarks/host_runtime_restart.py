#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

from porter.daemon import Porter
from porter.protocol import package


def payload(profile: str) -> tuple[str, dict]:
    if profile == "find-me":
        return "mailweb.request", {"request": {"mailweb": "0.6", "id": "06G1KAM4DBFS57CJHDTAMFDVG8", "method": "GET", "uri": "mailweb://find-me.local/stack", "headers": {}}}
    return "hdbe.call", {"operation": "info", "parameters": {}, "deposited_at_ms": int(time.time() * 1000)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=("find-me", "harmonicdb"), required=True)
    parser.add_argument("--host", required=True)
    parser.add_argument("--adapter", required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix=f"porter-restart-{args.profile}-") as folder:
        root = Path(folder)
        environment = dict(os.environ)
        environment.update({
            "PORTER_IPC": str(root),
            "FIND_ME_WORK_DIR": str(root / "find-me-application"),
            "HARMONIC_APPLICATION_DIR": str(root / "harmonic-application"),
            "PORTER_EXPERIMENT_CRASH_AFTER_DISPATCHES": "2",
        })
        porter = Porter(args.host, root, {})
        kind, body = payload(args.profile)
        identities = []
        for index in range(10):
            value = package("restart-sender", args.host, kind, body, reply_to="restart-sender", ttl=3600)
            value["package"] = f"PKG-{index:032x}"
            porter.deposit(value)
            identities.append(value["package"])
        command = [
            "porter-host-runtime", "--host", args.host, "--kind", kind,
            "--batch-size", "10", "--once", "--adapter", args.adapter,
        ]
        first = subprocess.run(command, env=environment, capture_output=True, text=True)
        after_crash = len(list((root / "host-runtime" / "dispatch-returned").glob("*.json")))
        environment.pop("PORTER_EXPERIMENT_CRASH_AFTER_DISPATCHES")
        second = subprocess.run(command, env=environment, capture_output=True, text=True)
        after_restart = len(list((root / "host-runtime" / "dispatch-returned").glob("*.json")))
        facts = len(list((root / "collections" / "facts").glob("CL-*.json")))
        print(json.dumps({
            "profile": args.profile,
            "first_exit": first.returncode,
            "runtime_returns_before_crash": after_crash,
            "restart_exit": second.returncode,
            "runtime_returns_after_restart": after_restart,
            "collection_facts": facts,
            "package_identities_unchanged": sorted(path.stem for path in (root / "host-runtime" / "dispatch-returned").glob("*.json")) == identities,
            "application_owned_crash_marker": (root / ("find-me-application" if args.profile == "find-me" else "harmonic-application") / "runtime-adapter-crash-once").exists(),
        }, indent=2))


if __name__ == "__main__":
    main()
