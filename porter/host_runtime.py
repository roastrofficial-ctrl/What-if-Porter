from __future__ import annotations

import argparse
import json
import os
import shlex
import signal
import selectors
import subprocess
import threading
import time
from pathlib import Path

from .custody import collect_package, recover_collections_for_runtime
from .candidates import inspect as inspect_candidates, settle as settle_candidate
from .lodgement import atomic_json, atomic_text

MAX_ADAPTER_CONTROL_CHARS = 65_536


def now_ms() -> int:
    return int(time.time() * 1000)


def append_json(path: Path, value: dict) -> None:
    """Append expendable operational telemetry.

    This journal is neither canonical evidence nor Runtime recovery state.  It
    is deliberately not forced to durable storage; loss may erase observation,
    never AC, CL, adapter control state, or application meaning.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as stream:
        stream.write(json.dumps(value, separators=(",", ":")) + "\n")
        stream.flush()


class Adapter:
    """Warm, local, language-neutral application boundary.

    A collected Package is written as one JSON line. The adapter returns control
    with one JSON line bearing the same dispatch identity. Nothing in this reply
    describes application success or PORTER disposition.
    """

    def __init__(self, command: str, startup_cancel: threading.Event | None = None):
        started = time.perf_counter_ns()
        self.process = subprocess.Popen(
            shlex.split(command),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        assert self.process.stdout is not None
        line = self._read_startup_control(startup_cancel)
        if not line:
            raise RuntimeError("application adapter exited before becoming ready")
        ready = json.loads(line)
        if (
            ready.get("contract") != "PORTER-HOST-ADAPTER/1"
            or ready.get("runtime_observation") != "ADAPTER_READY"
        ):
            raise RuntimeError("invalid application adapter readiness reply")
        self.startup_ms = (time.perf_counter_ns() - started) / 1e6

    def _read_startup_control(self, cancel: threading.Event | None) -> str:
        if cancel is None:
            return self._read_control("exited before becoming ready")
        assert self.process.stdout is not None
        selector = selectors.DefaultSelector()
        selector.register(self.process.stdout, selectors.EVENT_READ)
        try:
            while True:
                if cancel.is_set():
                    self.close(grace_seconds=0.05)
                    raise RuntimeError("application adapter startup cancelled")
                if selector.select(timeout=0.05):
                    return self._read_control("exited before becoming ready")
                if self.process.poll() is not None:
                    raise RuntimeError("application adapter exited before becoming ready")
        finally:
            selector.close()

    def _read_control(self, empty_reason: str) -> str:
        assert self.process.stdout is not None
        line = self.process.stdout.readline(MAX_ADAPTER_CONTROL_CHARS + 1)
        if not line:
            raise RuntimeError(f"application adapter {empty_reason}")
        if len(line) > MAX_ADAPTER_CONTROL_CHARS or not line.endswith("\n"):
            raise RuntimeError("application adapter control line exceeds limit")
        return line

    def dispatch(self, dispatch_id: str, collection: dict) -> dict:
        if self.process.poll() is not None:
            raise RuntimeError(f"application adapter exited {self.process.returncode}")
        assert self.process.stdin is not None
        assert self.process.stdout is not None
        self.process.stdin.write(
            json.dumps(
                {
                    "contract": "PORTER-HOST-ADAPTER/1",
                    "dispatch": dispatch_id,
                    "collection": collection,
                },
                separators=(",", ":"),
            )
            + "\n"
        )
        self.process.stdin.flush()
        line = self._read_control("exited without returning control")
        reply = json.loads(line)
        if (
            reply.get("contract") != "PORTER-HOST-ADAPTER/1"
            or reply.get("dispatch") != dispatch_id
            or reply.get("runtime_observation") != "ADAPTER_RETURNED_CONTROL"
        ):
            raise RuntimeError("invalid application adapter control reply")
        return reply

    def close(self, grace_seconds: float = 5.0) -> None:
        if self.process.poll() is None:
            if self.process.stdin is not None:
                self.process.stdin.close()
            try:
                self.process.wait(timeout=grace_seconds)
            except subprocess.TimeoutExpired:
                self.process.terminate()
                try:
                    self.process.wait(timeout=grace_seconds)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait()
        if self.process.stdout is not None:
            self.process.stdout.close()


class HostRuntime:
    def __init__(
        self,
        ipc: Path,
        host: str,
        adapter: Adapter,
        kinds: set[str],
        batch_size: int,
        idle_ms: int,
        journal: Path,
    ):
        if batch_size < 1:
            raise ValueError("batch size must be positive")
        self.ipc = ipc
        self.host = host
        self.adapter = adapter
        self.kinds = kinds
        self.batch_size = batch_size
        self.idle_ms = idle_ms
        self.journal = journal
        self.stopping = False
        self.sequence = 0
        self.recovering = True
        self.recovery_collections: list[dict] = []
        self.recovery_observation: dict | None = None

    def stop(self, *_args) -> None:
        self.stopping = True

    def candidates(self) -> list[str]:
        packages: dict[str, str] = {}
        offset = 0
        while len(packages) < self.batch_size:
            page = inspect_candidates(self.ipc, self.kinds, self.batch_size, offset)
            if not page:
                break
            packages.update(page)
            offset += len(page)
        projected = set(packages)
        if self.recovering:
            for fact in self.recovery_collections:
                if fact.get("collector") == self.host:
                    package = fact["package"]
                    if not self.kinds or package.get("kind") in self.kinds:
                        packages[package["package"]] = package["kind"]
        returned = self.ipc / "host-runtime" / "dispatch-returned"
        selected = []
        removed_projection = False
        for package_id, projected_kind in sorted(packages.items()):
            if (returned / f"{package_id}.json").exists():
                if package_id in projected:
                    settle_candidate(self.ipc, package_id)
                    removed_projection = True
                continue
            acceptance_path = self.ipc / "acceptances" / f"{package_id}.json"
            if not acceptance_path.exists():
                settle_candidate(self.ipc, package_id)
                removed_projection = True
                continue
            canonical = json.loads(acceptance_path.read_text())["package"]
            if canonical.get("kind") != projected_kind or (
                self.kinds and canonical.get("kind") not in self.kinds
            ):
                settle_candidate(self.ipc, package_id)
                removed_projection = True
                continue
            if (self.ipc / "collections" / "by-package" / package_id).exists():
                if package_id in projected:
                    settle_candidate(self.ipc, package_id)
                    removed_projection = True
                    continue
                # A canonical CL recovered without returned-control evidence is
                # precisely the crash gap that must be offered again. Its
                # association suppresses stale Porter projections, not recovery.
            selected.append(package_id)
        if removed_projection and len(selected) < self.batch_size:
            refill = [value for value in self.candidates() if value not in selected]
            selected.extend(refill[: self.batch_size - len(selected)])
        return selected[: self.batch_size]

    def visit(self) -> int:
        began = time.perf_counter_ns()
        visit_id = f"VISIT-{self.host}-{now_ms()}-{self.sequence}"
        self.sequence += 1
        if self.recovering:
            self.recovery_observation = recover_collections_for_runtime(self.ipc)
            self.recovery_collections = self.recovery_observation["collections"]
        inspection_started = time.perf_counter_ns()
        selected = self.candidates()[: self.batch_size]
        inspection_ms = (time.perf_counter_ns() - inspection_started) / 1e6
        self.recovering = False
        dispatched = 0
        for package_id in selected:
            if self.stopping:
                break
            collection_started = time.perf_counter_ns()
            # The first visit recovered every canonical CL association. New CL
            # publication reserves its association before the canonical fact,
            # so this lifecycle need not rescan the growing CL directory merely
            # to establish that a new Package has not already been collected.
            collection = collect_package(
                self.ipc, package_id, self.host, scan_missing=False
            )
            collection_ms = (time.perf_counter_ns() - collection_started) / 1e6
            dispatch_id = f"{visit_id}:{dispatched + 1}"
            dispatch_started = time.perf_counter_ns()
            append_json(
                self.journal,
                {
                    "observation": "DISPATCH_BEGAN",
                    "at_ms": now_ms(),
                    "host": self.host,
                    "visit": visit_id,
                    "dispatch": dispatch_id,
                    "package": package_id,
                    "collection": collection["collection"],
                    "collection_ms": round(collection_ms, 3),
                },
            )
            reply = self.adapter.dispatch(dispatch_id, collection)
            dispatch_ms = (time.perf_counter_ns() - dispatch_started) / 1e6
            atomic_json(
                self.ipc
                / "host-runtime"
                / "dispatch-returned"
                / f"{package_id}.json",
                {
                    "runtime_observation": "ADAPTER_RETURNED_CONTROL",
                    "at_ms": now_ms(),
                    "host": self.host,
                    "package": package_id,
                    "collection": collection["collection"],
                    "dispatch": dispatch_id,
                },
            )
            append_json(
                self.journal,
                {
                    "observation": "ADAPTER_RETURNED_CONTROL",
                    "at_ms": now_ms(),
                    "host": self.host,
                    "visit": visit_id,
                    "dispatch": dispatch_id,
                    "package": package_id,
                    "collection": collection["collection"],
                    "dispatch_ms": round(dispatch_ms, 3),
                },
            )
            dispatched += 1
        if selected:
            append_json(
                self.journal,
                {
                    "observation": "VISIT_ENDED",
                    "at_ms": now_ms(),
                    "host": self.host,
                    "visit": visit_id,
                    "selected": len(selected),
                    "dispatched": dispatched,
                    "inspection": "PORTER-CANDIDATES/1",
                    "inspection_ms": round(inspection_ms, 3),
                    "visit_ms": round((time.perf_counter_ns() - began) / 1e6, 3),
                },
            )
        return dispatched

    def run(self, once: bool = False) -> None:
        for named_signal in (signal.SIGTERM, signal.SIGINT):
            signal.signal(named_signal, self.stop)
        atomic_text(
            self.ipc / "host.ready",
            f"{self.host} Host Runtime is locally active; arrival cannot wake it.\n",
        )
        append_json(
            self.journal,
            {
                "observation": "ADAPTER_READY",
                "at_ms": now_ms(),
                "host": self.host,
                "adapter_startup_ms": round(
                    float(getattr(self.adapter, "startup_ms", 0.0)), 3
                ),
            },
        )
        try:
            while not self.stopping:
                dispatched = self.visit()
                if once:
                    break
                if dispatched == 0:
                    time.sleep(self.idle_ms / 1000)
        finally:
            self.adapter.close()


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description="Local, pull-only PORTER Host Runtime")
    value.add_argument("--ipc", default=os.getenv("PORTER_IPC", "/porter"))
    value.add_argument("--host", required=True)
    value.add_argument("--adapter", required=True)
    value.add_argument("--kind", action="append", default=[])
    value.add_argument("--batch-size", type=int, default=10)
    value.add_argument("--idle-ms", type=int, default=100)
    value.add_argument("--journal")
    value.add_argument("--once", action="store_true")
    value.add_argument("--max-inflight-offers", type=int, default=1)
    value.add_argument("--elastic-capacity", action="store_true")
    value.add_argument("--elastic-slow-offer-ms", type=float, default=5)
    value.add_argument("--elastic-shed-after-ms", type=float, default=1000)
    value.add_argument("--elastic-evidence-window", type=int, default=8)
    value.add_argument("--elastic-minimum-residence-ms", type=float, default=50)
    value.add_argument("--elastic-inspection-interval-ms", type=float, default=50)
    value.add_argument("--elastic-acquisition-retry-ms", type=float, default=1000)
    publication = value.add_mutually_exclusive_group()
    publication.add_argument(
        "--serial-publication", dest="serial_publication", action="store_true"
    )
    publication.add_argument(
        "--parallel-publication", dest="serial_publication", action="store_false"
    )
    value.set_defaults(serial_publication=True)
    return value


def main() -> None:
    args = parser().parse_args()
    ipc = Path(args.ipc)
    common = {
        "ipc": ipc, "host": args.host, "kinds": set(args.kind),
        "batch_size": args.batch_size, "idle_ms": args.idle_ms,
        "journal": Path(args.journal or ipc / "host-runtime.jsonl"),
    }
    if args.max_inflight_offers == 1:
        runtime = HostRuntime(adapter=Adapter(args.adapter), **common)
    elif args.elastic_capacity:
        from .opportunities import ElasticOpportunityRuntime
        acquisition_cancel = threading.Event()
        runtime = ElasticOpportunityRuntime(
            adapters=[Adapter(args.adapter)],
            adapter_factory=lambda: Adapter(
                args.adapter, startup_cancel=acquisition_cancel
            ),
            acquisition_cancel=acquisition_cancel,
            acquisition_retry_ms=args.elastic_acquisition_retry_ms,
            maximum_adapters=args.max_inflight_offers,
            slow_offer_ms=args.elastic_slow_offer_ms,
            shed_after_ms=args.elastic_shed_after_ms,
            evidence_window=args.elastic_evidence_window,
            minimum_capacity_residence_ms=args.elastic_minimum_residence_ms,
            inspection_interval_ms=args.elastic_inspection_interval_ms,
            serial_publication=args.serial_publication,
            **common,
        )
    else:
        if args.max_inflight_offers < 1:
            raise ValueError("max inflight offers must be positive")
        from .opportunities import BoundedOpportunityRuntime
        adapters = []
        try:
            for _ in range(args.max_inflight_offers):
                adapters.append(Adapter(args.adapter))
        except BaseException:
            for adapter in adapters:
                adapter.close()
            raise
        runtime = BoundedOpportunityRuntime(
            adapters=adapters,
            max_inflight_offers=args.max_inflight_offers,
            serial_publication=args.serial_publication,
            **common,
        )
    runtime.run(args.once)


if __name__ == "__main__":
    main()
