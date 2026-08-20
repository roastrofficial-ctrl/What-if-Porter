#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

from porter.daemon import Porter
from porter.host_runtime import Adapter, HostRuntime
from porter.protocol import package


def main():
    with tempfile.TemporaryDirectory(prefix="porter-third-host-") as folder:
        root = Path(folder)
        state = root / "application"
        value = package("sender", "tiny-host", "tiny.observe", {"message": "semantics live elsewhere"}, ttl=3600)
        porter = Porter("tiny-host", root, {})
        porter.deposit(value)
        environment = {
            "PORTER_IPC": str(root),
            "TINY_HOST_STATE": str(state),
        }
        previous = {name: os.environ.get(name) for name in environment}
        os.environ.update(environment)
        script = Path(__file__).parents[1] / "examples" / "tiny_host_adapter.py"
        adapter = Adapter(f"{sys.executable} {script}")
        try:
            runtime = HostRuntime(root, "tiny-host", adapter, {"tiny.observe"}, 1, 100, root / "runtime.jsonl")
            dispatched = runtime.visit()
        finally:
            adapter.close()
            for name, old in previous.items():
                if old is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = old
        interfaces = Path("/proc/net/dev").read_text() if Path("/proc/net/dev").exists() else "unavailable"
        non_loopback = [line.split(":", 1)[0].strip() for line in interfaces.splitlines() if ":" in line and line.split(":", 1)[0].strip() != "lo"]
        tcp = Path("/proc/net/tcp").read_text().splitlines() if Path("/proc/net/tcp").exists() else []
        listeners = [line for line in tcp[1:] if line.split()[3] == "0A"]
        result = {
            "host": "tiny-host", "runtime_source_changed_for_host": False,
            "dispatched": dispatched, "collection_facts": len(list((root / "collections" / "facts").glob("CL-*.json"))),
            "application_facts": len(list(state.glob("PKG-*.json"))),
            "returns": len(list((root / "tickets").glob("CT-*.json"))),
            "non_loopback_interfaces": non_loopback,
            "application_listener_required": False,
            "tcp_listeners": len(listeners),
        }
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
