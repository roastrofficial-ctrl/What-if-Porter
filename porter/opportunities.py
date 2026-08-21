from __future__ import annotations

import json
import queue
import signal
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from .custody import collect_package, recover_collections_for_runtime
from .host_runtime import HostRuntime, append_json, now_ms
from .lodgement import atomic_json, atomic_text


class BoundedOpportunityRuntime(HostRuntime):
    """Experimental bounded local scheduling under the frozen Runtime contract.

    One adapter instance receives at most one offer at a time.  The bound covers
    both Collection publication in progress and offers awaiting local control.
    Futures and adapter assignment are process-local operational state only.
    """

    def __init__(self, *args, adapters: list, max_inflight_offers: int,
                 scan_missing_collections: bool = False,
                 allow_partial_pool: bool = False,
                 serial_publication: bool = True, **kwargs):
        if max_inflight_offers < 1:
            raise ValueError("max_inflight_offers must be positive")
        if len(adapters) < max_inflight_offers and not allow_partial_pool:
            raise ValueError("one adapter instance is required per inflight offer")
        super().__init__(*args, adapter=adapters[0], **kwargs)
        self.adapters = adapters
        self.max_inflight_offers = max_inflight_offers
        self.scan_missing_collections = scan_missing_collections
        self.serial_publication = serial_publication
        self.available: queue.SimpleQueue = queue.SimpleQueue()
        for adapter in adapters:
            self.available.put(adapter)
        self.available_count = len(adapters)
        self.executor = ThreadPoolExecutor(
            max_workers=max_inflight_offers, thread_name_prefix="porter-opportunity"
        )
        self.inflight: dict[Future, tuple[str, object]] = {}
        self.started_at: dict[Future, float] = {}
        self.offer_ms: list[float] = []
        self.dispatch_began_at: dict[str, float] = {}
        self.submitted: set[str] = set()
        self.control_returns = 0
        self.operational_errors: list[tuple[str, BaseException]] = []
        self.maximum_inflight = 0
        self.publication_in_progress = 0
        self.maximum_opportunities = 0

    def _offer(self, package_id: str, adapter, dispatch_id: str):
        collection_started = time.perf_counter_ns()
        collection = collect_package(
            self.ipc, package_id, self.host,
            scan_missing=self.scan_missing_collections,
        )
        collection_ms = (time.perf_counter_ns() - collection_started) / 1e6
        return self._dispatch_collected(
            package_id, adapter, dispatch_id, collection, collection_ms
        )

    def _dispatch_collected(self, package_id: str, adapter, dispatch_id: str,
                            collection: dict, collection_ms: float):
        append_json(self.journal, {
            "observation": "DISPATCH_BEGAN", "at_ms": now_ms(),
            "host": self.host, "dispatch": dispatch_id, "package": package_id,
            "collection": collection["collection"],
            "collection_ms": round(collection_ms, 3),
        })
        dispatch_started = time.perf_counter_ns()
        self.dispatch_began_at[package_id] = time.monotonic()
        adapter.dispatch(dispatch_id, collection)
        dispatch_ms = (time.perf_counter_ns() - dispatch_started) / 1e6
        # Capacity pressure is application control latency, not the following
        # local marker publication or the cadence at which the visit reaps it.
        self.dispatch_began_at.pop(package_id, None)
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
        return collection, dispatch_ms

    def after_publication(self, _package_id: str, _collection: dict) -> None:
        """Non-durable experiment hook at the existing CL-before-offer gap."""

    def _submit_offer(self, package_id: str, adapter, dispatch_id: str) -> Future | None:
        if not self.serial_publication:
            return self.executor.submit(self._offer, package_id, adapter, dispatch_id)
        began = time.perf_counter_ns()
        self.publication_in_progress = 1
        self.maximum_opportunities = max(
            self.maximum_opportunities, len(self.inflight) + self.publication_in_progress
        )
        try:
            collection = collect_package(
                self.ipc, package_id, self.host,
                scan_missing=self.scan_missing_collections,
            )
            collection_ms = (time.perf_counter_ns() - began) / 1e6
            self.after_publication(package_id, collection)
        except BaseException as exc:
            self.operational_errors.append((package_id, exc))
            self.submitted.discard(package_id)
            self.available.put(adapter)
            self.available_count += 1
            return None
        finally:
            self.publication_in_progress = 0
        return self.executor.submit(
            self._dispatch_collected, package_id, adapter, dispatch_id,
            collection, collection_ms,
        )

    def _reap(self) -> int:
        returned = 0
        for future, (package_id, adapter) in list(self.inflight.items()):
            if not future.done():
                continue
            del self.inflight[future]
            started_at = self.started_at.pop(future)
            self.submitted.discard(package_id)
            try:
                _collection, dispatch_ms = future.result()
                self.offer_ms.append(dispatch_ms)
                self.dispatch_began_at.pop(package_id, None)
                returned += 1
                self.control_returns += 1
                self.available.put(adapter)
                self.available_count += 1
            except BaseException as exc:
                self.dispatch_began_at.pop(package_id, None)
                self.operational_errors.append((package_id, exc))
                adapter.close()
        return returned

    def visit(self) -> int:
        if self.recovering:
            self.recovery_observation = recover_collections_for_runtime(self.ipc)
            self.recovery_collections = self.recovery_observation["collections"]
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
        self.recovering = False
        visit_id = f"VISIT-{self.host}-{now_ms()}-{self.sequence}"
        self.sequence += 1
        for index, package_id in enumerate(selected, 1):
            adapter = self.available.get()
            self.available_count -= 1
            dispatch_id = f"{visit_id}:{index}"
            self.submitted.add(package_id)
            future = self._submit_offer(package_id, adapter, dispatch_id)
            if future is None:
                continue
            self.inflight[future] = (package_id, adapter)
            self.started_at[future] = time.monotonic()
        self.maximum_inflight = max(self.maximum_inflight, len(self.inflight))
        self.maximum_opportunities = max(
            self.maximum_opportunities, len(self.inflight) + self.publication_in_progress
        )
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


class ElasticOpportunityRuntime(BoundedOpportunityRuntime):
    """Locally elastic variant; only an executing visit may resize capacity."""

    def __init__(self, *args, adapter_factory, maximum_adapters: int,
                 slow_offer_ms: float = 5, shed_after_ms: float = 1000,
                 evidence_window: int = 8,
                 minimum_capacity_residence_ms: float = 50,
                 inspection_interval_ms: float = 50,
                 acquisition_cancel: threading.Event | None = None,
                 acquisition_retry_ms: float = 1000,
                 **kwargs):
        adapters = kwargs.pop("adapters")
        if len(adapters) != 1:
            raise ValueError("elastic runtime starts with exactly one warm adapter")
        if maximum_adapters < 1:
            raise ValueError("maximum adapters must be positive")
        if evidence_window < 1:
            raise ValueError("evidence window must be positive")
        if (slow_offer_ms < 0 or shed_after_ms < 0
                or minimum_capacity_residence_ms < 0 or inspection_interval_ms < 0
                or acquisition_retry_ms < 0):
            raise ValueError("elastic timing values cannot be negative")
        super().__init__(
            *args, adapters=adapters, max_inflight_offers=maximum_adapters,
            allow_partial_pool=True, **kwargs
        )
        self.adapter_factory = adapter_factory
        self.maximum_adapters = maximum_adapters
        self.slow_offer_ms = slow_offer_ms
        self.shed_after_ms = shed_after_ms
        self.evidence_window = evidence_window
        self.minimum_capacity_residence_ms = minimum_capacity_residence_ms
        self.inspection_interval_ms = inspection_interval_ms
        self.last_pressure_at = time.monotonic()
        self.last_capacity_change_at = self.last_pressure_at
        self.capacity_events: list[tuple[str, int]] = []
        self.acquisition_cancel = acquisition_cancel or threading.Event()
        self.acquisition_retry_ms = acquisition_retry_ms
        self.last_acquisition_failure_at = float("-inf")
        self.starting: dict[Future, float] = {}
        self.startup_ms: list[float] = []
        self.candidate_snapshot: list[str] = []
        self.last_inspection_at = float("-inf")
        self.inspection_count = 0
        self.inspection_ms = 0.0

    def _refresh_snapshot(self) -> None:
        began = time.perf_counter_ns()
        self.candidate_snapshot = [
            package_id for package_id in self.candidates()
            if package_id not in self.submitted
        ]
        self.inspection_ms += (time.perf_counter_ns() - began) / 1e6
        self.inspection_count += 1
        self.last_inspection_at = time.monotonic()

    def _still_candidate(self, package_id: str) -> bool:
        """Cheaply revalidate cached opportunity without re-enumerating."""
        if package_id in self.submitted:
            return False
        if (self.ipc / "host-runtime" / "dispatch-returned" / f"{package_id}.json").exists():
            return False
        acceptance = self.ipc / "acceptances" / f"{package_id}.json"
        if not acceptance.exists():
            return False
        canonical = json.loads(acceptance.read_text())["package"]
        if self.kinds and canonical.get("kind") not in self.kinds:
            return False
        if (self.ipc / "collections" / "by-package" / package_id).exists():
            return False
        return True

    def _reap(self) -> int:
        self._reap_starting()
        returned = super()._reap()
        if len(self.offer_ms) > self.evidence_window:
            del self.offer_ms[:-self.evidence_window]
        return returned

    def _reap_starting(self) -> None:
        for future, began in list(self.starting.items()):
            if not future.done():
                continue
            del self.starting[future]
            try:
                adapter = future.result()
            except BaseException as exc:
                self.operational_errors.append(("CAPACITY_ACQUISITION", exc))
                self.capacity_events.append(("FAILED", len(self.adapters)))
                self.last_acquisition_failure_at = time.monotonic()
                continue
            elapsed = (time.monotonic() - began) * 1000
            self.startup_ms.append(elapsed)
            if self.stopping:
                adapter.close()
                self.capacity_events.append(("CANCELLED", len(self.adapters)))
                continue
            self.adapters.append(adapter)
            self.available.put(adapter)
            self.available_count += 1
            self.capacity_events.append(("GROW", len(self.adapters)))

    @staticmethod
    def _discard_late_adapter(future: Future) -> None:
        if future.cancelled():
            return
        try:
            future.result().close()
        except BaseException:
            pass

    def _slow_evidence(self) -> int:
        completed = sum(
            value >= self.slow_offer_ms
            for value in self.offer_ms[-self.evidence_window:]
        )
        now = time.monotonic()
        active = sum(
            began is not None and (now - began) * 1000 >= self.slow_offer_ms
            for package_id, _adapter in self.inflight.values()
            for began in [self.dispatch_began_at.get(package_id)]
        )
        return completed + active

    def _cheap_window(self) -> bool:
        recent = self.offer_ms[-self.evidence_window:]
        return (
            len(recent) == self.evidence_window
            and all(value < self.slow_offer_ms for value in recent)
            and not self.dispatch_began_at
        )

    def _grow(self) -> None:
        committed = len(self.adapters) + len(self.starting)
        if committed >= self.maximum_adapters:
            return
        if ((time.monotonic() - self.last_acquisition_failure_at) * 1000
                < self.acquisition_retry_ms):
            return
        future = self.executor.submit(self.adapter_factory)
        self.starting[future] = time.monotonic()
        self.capacity_events.append(("START", committed + 1))
        self.last_capacity_change_at = time.monotonic()

    def _shed_one(self) -> None:
        if len(self.adapters) <= 1 or self.available_count <= 1:
            return
        adapter = self.available.get()
        self.available_count -= 1
        self.adapters.remove(adapter)
        adapter.close()
        self.capacity_events.append(("SHED", len(self.adapters)))
        self.last_capacity_change_at = time.monotonic()

    def visit(self) -> int:
        if self.recovering:
            self.recovery_observation = recover_collections_for_runtime(self.ipc)
            self.recovery_collections = self.recovery_observation["collections"]
        returned = self._reap()
        if self.stopping:
            return returned

        now = time.monotonic()
        available_capacity = min(
            self.max_inflight_offers - len(self.inflight) - len(self.starting),
            self.available_count,
        )
        if (
            not self.candidate_snapshot and available_capacity > 0
            and (now - self.last_inspection_at) * 1000 >= self.inspection_interval_ms
        ):
            self._refresh_snapshot()
            self.recovering = False

        pressure = bool(self.candidate_snapshot) and (
            len(self.candidate_snapshot) > self.available_count or bool(self.inflight)
        )
        if pressure:
            self.last_pressure_at = time.monotonic()
            # One slow offer earns a second lane so it cannot monopolise the
            # Host. Each further lane requires proportionally more independent
            # recent/active evidence; one outlier cannot inflate the whole pool.
            if self._slow_evidence() >= len(self.adapters) + len(self.starting):
                self._grow()
            elif (
                len(self.adapters) > 1 and self._cheap_window()
                and (time.monotonic() - self.last_capacity_change_at) * 1000
                    >= self.minimum_capacity_residence_ms
            ):
                self._shed_one()
        elif (
            not self.candidate_snapshot and not self.inflight and len(self.adapters) > 1
            and (time.monotonic() - self.last_pressure_at) * 1000 >= self.shed_after_ms
        ):
            self._shed_one()

        capacity = min(
            self.max_inflight_offers - len(self.inflight) - len(self.starting),
            self.available_count,
        )
        visit_id = f"VISIT-{self.host}-{now_ms()}-{self.sequence}"
        self.sequence += 1
        selected = []
        while self.candidate_snapshot and len(selected) < capacity:
            package_id = self.candidate_snapshot.pop(0)
            if self._still_candidate(package_id):
                selected.append(package_id)
        for index, package_id in enumerate(selected, 1):
            adapter = self.available.get()
            self.available_count -= 1
            dispatch_id = f"{visit_id}:{index}"
            self.submitted.add(package_id)
            future = self._submit_offer(package_id, adapter, dispatch_id)
            if future is None:
                continue
            self.inflight[future] = (package_id, adapter)
            self.started_at[future] = time.monotonic()
        self.maximum_inflight = max(self.maximum_inflight, len(self.inflight))
        self.maximum_opportunities = max(
            self.maximum_opportunities,
            len(self.inflight) + self.publication_in_progress + len(self.starting),
        )
        return returned

    def close(self, grace_seconds: float = 5.0) -> None:
        self.stop()
        self.acquisition_cancel.set()
        self._reap_starting()
        for future in self.starting:
            if not future.cancel():
                future.add_done_callback(self._discard_late_adapter)
        self.starting.clear()
        super().close(grace_seconds=grace_seconds)
