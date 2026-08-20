from __future__ import annotations

import queue
import signal
import time
from concurrent.futures import Future, ThreadPoolExecutor
from .custody import collect_package, recover_collections
from .host_runtime import HostRuntime, append_json, now_ms
from .lodgement import atomic_json, atomic_text


class BoundedOpportunityRuntime(HostRuntime):
    """Experimental bounded local scheduling under the frozen Runtime contract.

    One adapter instance receives at most one offer at a time.  The bound covers
    both Collection publication in progress and offers awaiting local control.
    Futures and adapter assignment are process-local operational state only.
    """

    def __init__(self, *args, adapters: list, max_inflight_offers: int,
                 scan_missing_collections: bool = False, **kwargs):
        if max_inflight_offers < 1:
            raise ValueError("max_inflight_offers must be positive")
        if len(adapters) < max_inflight_offers:
            raise ValueError("one adapter instance is required per inflight offer")
        super().__init__(*args, adapter=adapters[0], **kwargs)
        self.adapters = adapters
        self.max_inflight_offers = max_inflight_offers
        self.scan_missing_collections = scan_missing_collections
        self.available: queue.SimpleQueue = queue.SimpleQueue()
        for adapter in adapters:
            self.available.put(adapter)
        self.available_count = len(adapters)
        self.executor = ThreadPoolExecutor(
            max_workers=max_inflight_offers, thread_name_prefix="porter-opportunity"
        )
        self.inflight: dict[Future, tuple[str, object]] = {}
        self.submitted: set[str] = set()
        self.control_returns = 0
        self.operational_errors: list[tuple[str, BaseException]] = []
        self.maximum_inflight = 0

    def _offer(self, package_id: str, adapter, dispatch_id: str):
        collection_started = time.perf_counter_ns()
        collection = collect_package(
            self.ipc, package_id, self.host,
            scan_missing=self.scan_missing_collections,
        )
        collection_ms = (time.perf_counter_ns() - collection_started) / 1e6
        append_json(self.journal, {
            "observation": "DISPATCH_BEGAN", "at_ms": now_ms(),
            "host": self.host, "dispatch": dispatch_id, "package": package_id,
            "collection": collection["collection"],
            "collection_ms": round(collection_ms, 3),
        })
        dispatch_started = time.perf_counter_ns()
        adapter.dispatch(dispatch_id, collection)
        dispatch_ms = (time.perf_counter_ns() - dispatch_started) / 1e6
        atomic_json(
            self.ipc / "host-runtime" / "dispatch-returned" / f"{package_id}.json",
            {
                "runtime_observation": "ADAPTER_RETURNED_CONTROL",
                "at_ms": now_ms(), "host": self.host,
                "package": package_id, "collection": collection["collection"],
                "dispatch": dispatch_id,
            },
        )
        append_json(self.journal, {
            "observation": "ADAPTER_RETURNED_CONTROL", "at_ms": now_ms(),
            "host": self.host, "dispatch": dispatch_id, "package": package_id,
            "collection": collection["collection"],
            "dispatch_ms": round(dispatch_ms, 3),
        })
        return collection

    def _reap(self) -> int:
        returned = 0
        for future, (package_id, adapter) in list(self.inflight.items()):
            if not future.done():
                continue
            del self.inflight[future]
            self.submitted.discard(package_id)
            try:
                future.result()
                returned += 1
                self.control_returns += 1
                self.available.put(adapter)
                self.available_count += 1
            except BaseException as exc:
                self.operational_errors.append((package_id, exc))
                adapter.close()
        return returned

    def visit(self) -> int:
        if self.recovering:
            recover_collections(self.ipc)
            self.recovering = False
        returned = self._reap()
        if self.stopping:
            return returned
        capacity = min(
            self.max_inflight_offers - len(self.inflight), self.available_count
        )
        if capacity <= 0:
            return returned
        selected = [
            package_id for package_id in self.candidates()
            if package_id not in self.submitted
        ][:capacity]
        visit_id = f"VISIT-{self.host}-{now_ms()}-{self.sequence}"
        self.sequence += 1
        for index, package_id in enumerate(selected, 1):
            adapter = self.available.get()
            self.available_count -= 1
            dispatch_id = f"{visit_id}:{index}"
            self.submitted.add(package_id)
            future = self.executor.submit(
                self._offer, package_id, adapter, dispatch_id
            )
            self.inflight[future] = (package_id, adapter)
        self.maximum_inflight = max(self.maximum_inflight, len(self.inflight))
        return returned

    def drain(self, total: int, poll_ms: int = 1) -> int:
        while self.control_returns < total and not self.stopping:
            self.visit()
            if self.control_returns < total:
                time.sleep(poll_ms / 1000)
        self._reap()
        return self.control_returns

    def close(self, grace_seconds: float = 5.0) -> None:
        self.stop()
        deadline = time.monotonic() + grace_seconds
        while self.inflight and time.monotonic() < deadline:
            self._reap()
            if self.inflight:
                time.sleep(0.005)
        if self.inflight:
            for adapter in self.adapters:
                adapter.close(grace_seconds=0.05)
            deadline = time.monotonic() + 1
            while self.inflight and time.monotonic() < deadline:
                self._reap()
                time.sleep(0.005)
        else:
            for adapter in self.adapters:
                adapter.close()
        self.executor.shutdown(wait=not self.inflight, cancel_futures=True)

    def run(self, once: bool = False) -> None:
        for named_signal in (signal.SIGTERM, signal.SIGINT):
            signal.signal(named_signal, self.stop)
        atomic_text(
            self.ipc / "host.ready",
            f"{self.host} Host Runtime is locally active; arrival cannot wake it.\n",
        )
        try:
            while not self.stopping:
                returned = self.visit()
                if once:
                    while self.inflight and not self.stopping:
                        time.sleep(.001)
                        self._reap()
                    break
                if returned == 0:
                    time.sleep(self.idle_ms / 1000)
        finally:
            self.close()
