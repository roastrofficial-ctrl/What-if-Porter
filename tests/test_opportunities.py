import threading
import time
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from porter.daemon import Porter
from porter.custody import collect_package
from porter.host_runtime import HostRuntime
from porter.opportunities import BoundedOpportunityRuntime, ElasticOpportunityRuntime
import porter.opportunities as opportunity_module
from porter.protocol import package


class GateAdapter:
    def __init__(self, gate=None, delay=0):
        self.gate = gate
        self.delay = delay
        self.collections = []

    def dispatch(self, dispatch_id, collection):
        self.collections.append(collection)
        if self.gate is not None:
            self.gate.wait()
        if self.delay:
            time.sleep(self.delay)
        return {"contract": "PORTER-HOST-ADAPTER/1", "dispatch": dispatch_id,
                "runtime_observation": "ADAPTER_RETURNED_CONTROL"}

    def close(self, grace_seconds=0):
        if self.gate is not None:
            self.gate.set()


class PatternAdapter(GateAdapter):
    def __init__(self, delays_ms):
        super().__init__()
        self.delays_ms = delays_ms

    def dispatch(self, dispatch_id, collection):
        self.collections.append(collection)
        number = collection["package"]["payload"]["n"]
        delay = self.delays_ms[number]
        if delay:
            time.sleep(delay / 1000)
        return {"contract": "PORTER-HOST-ADAPTER/1", "dispatch": dispatch_id,
                "runtime_observation": "ADAPTER_RETURNED_CONTROL"}


class OpportunitySchedulingTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.porter = Porter("host", self.root, {})

    def tearDown(self):
        self.temp.cleanup()

    def accept(self, count):
        values = [package("sender", "host", "demo.work", {"n": n}) for n in range(count)]
        for value in values:
            self.porter.deposit(value)
        return values

    def scheduled(self, adapters, maximum):
        return BoundedOpportunityRuntime(
            ipc=self.root, host="host", adapters=adapters,
            max_inflight_offers=maximum, kinds={"demo.work"},
            batch_size=max(10, maximum), idle_ms=10,
            journal=self.root / "runtime.jsonl",
        )

    def wait_for(self, predicate, seconds=2):
        deadline = time.monotonic() + seconds
        while not predicate() and time.monotonic() < deadline:
            time.sleep(.005)
        self.assertTrue(predicate())

    def test_bound_covers_collection_and_outstanding_offer(self):
        self.accept(10)
        gate = threading.Event()
        adapters = [GateAdapter(gate) for _ in range(3)]
        runtime = self.scheduled(adapters, 3)
        runtime.visit()
        self.wait_for(lambda: len(list((self.root / "collections" / "facts").glob("CL-*.json"))) == 3)
        for _ in range(5):
            runtime.visit()
        self.assertEqual(len(runtime.inflight), 3)
        # Inbox is a byte projection and may briefly coexist while the three
        # independent materializations finish; its timing is not custody truth.
        self.assertGreaterEqual(len(list((self.root / "inbox").glob("PKG-*.json"))), 7)
        gate.set()
        self.assertEqual(runtime.drain(10), 10)
        runtime.close()

    def test_hung_offer_does_not_monopolise_unrelated_capacity(self):
        self.accept(4)
        hung = threading.Event()
        runtime = self.scheduled([GateAdapter(hung), GateAdapter(delay=.01)], 2)
        runtime.visit()
        self.wait_for(lambda: sum(len(adapter.collections) for adapter in runtime.adapters) >= 2)
        deadline = time.monotonic() + 2
        while runtime.control_returns < 3 and time.monotonic() < deadline:
            runtime.visit()
            time.sleep(.005)
        self.assertEqual(runtime.control_returns, 3)
        self.assertEqual(len(runtime.inflight), 1)
        self.assertEqual(runtime.maximum_inflight, 2)
        began = time.perf_counter()
        runtime.close(grace_seconds=.02)
        self.assertLess(time.perf_counter() - began, .5)

    def test_multiple_runtimes_preserve_one_cl_but_duplicate_offer(self):
        self.accept(1)
        first_adapter, second_adapter = GateAdapter(), GateAdapter()
        barrier = threading.Barrier(2)
        class CompetingRuntime(HostRuntime):
            def candidates(inner):
                selected = super(CompetingRuntime, inner).candidates()
                barrier.wait()
                return selected
        first = CompetingRuntime(self.root, "host", first_adapter, {"demo.work"}, 1, 10, self.root / "first.jsonl")
        second = CompetingRuntime(self.root, "host", second_adapter, {"demo.work"}, 1, 10, self.root / "second.jsonl")
        threads = [threading.Thread(target=runtime.visit) for runtime in (first, second)]
        for thread in threads: thread.start()
        for thread in threads: thread.join()
        self.assertEqual(len(list((self.root / "collections" / "facts").glob("CL-*.json"))), 1)
        self.assertEqual(len(first_adapter.collections) + len(second_adapter.collections), 2)

    def test_scheduled_offers_add_no_durable_running_state(self):
        self.accept(2)
        gate = threading.Event()
        runtime = self.scheduled([GateAdapter(gate), GateAdapter(gate)], 2)
        runtime.visit()
        self.wait_for(lambda: len(list((self.root / "collections" / "facts").glob("CL-*.json"))) == 2)
        names = {path.name for path in (self.root / "host-runtime").glob("**/*") if path.is_file()}
        self.assertFalse(any(word in name.lower() for name in names for word in ("running", "processing", "worker")))
        gate.set()
        runtime.drain(2)
        runtime.close()

    def test_crash_shape_with_two_outstanding_one_returned_one_porter_owned(self):
        self.accept(4)
        first_gate, third_gate = threading.Event(), threading.Event()
        adapters = [GateAdapter(first_gate), GateAdapter(), GateAdapter(third_gate)]
        runtime = self.scheduled(adapters, 3)
        runtime.visit()
        self.wait_for(lambda: len(list((self.root / "collections" / "facts").glob("CL-*.json"))) == 3)
        self.wait_for(lambda: len(list((self.root / "host-runtime" / "dispatch-returned").glob("*.json"))) == 1)
        self.assertEqual(len(runtime.inflight), 3)  # return is not reaped yet
        self.assertEqual(len(list((self.root / "inbox").glob("PKG-*.json"))), 1)
        self.assertEqual(len(list((self.root / "collections" / "facts").glob("CL-*.json"))), 3)
        # No durable state says the other two offers were "running". Simulate
        # process loss by releasing test threads only for local cleanup.
        runtime.stop()
        first_gate.set(); third_gate.set()
        while runtime.inflight:
            runtime.visit(); time.sleep(.002)
        runtime.close()

    def elastic(self, factory, first, maximum=4, slow_ms=15, shed_ms=20):
        return ElasticOpportunityRuntime(
            ipc=self.root, host="host", adapters=[first],
            adapter_factory=factory, maximum_adapters=maximum,
            slow_offer_ms=slow_ms, shed_after_ms=shed_ms,
            kinds={"demo.work"}, batch_size=10, idle_ms=1,
            journal=self.root / "elastic.jsonl",
        )

    def test_arrival_alone_cannot_create_elastic_capacity(self):
        created = []
        def factory():
            created.append(True)
            return GateAdapter()
        runtime = self.elastic(factory, GateAdapter())
        self.accept(10)
        time.sleep(.03)
        self.assertEqual(len(runtime.adapters), 1)
        self.assertEqual(created, [])
        runtime.close()

    def test_cheap_work_does_not_earn_growth(self):
        self.accept(20)
        runtime = self.elastic(GateAdapter, GateAdapter(), slow_ms=20)
        self.assertEqual(runtime.drain(20), 20)
        self.assertEqual(runtime.capacity_events, [])
        self.assertEqual(len(runtime.adapters), 1)
        runtime.close()

    def test_slow_pressure_grows_then_local_idleness_sheds(self):
        self.accept(12)
        runtime = self.elastic(
            lambda: GateAdapter(delay=.03), GateAdapter(delay=.03),
            slow_ms=10, shed_ms=10,
        )
        runtime.visit()
        time.sleep(.012)
        deadline = time.monotonic() + 2
        while runtime.control_returns < 12 and time.monotonic() < deadline:
            runtime.visit()
            time.sleep(.002)
        self.assertEqual(runtime.control_returns, 12)
        self.assertTrue(any(event == "GROW" for event, _ in runtime.capacity_events))
        self.assertGreater(runtime.maximum_inflight, 1)
        time.sleep(.012)
        while len(runtime.adapters) > 1:
            runtime.visit()
        self.assertEqual(len(runtime.adapters), 1)
        self.assertEqual(runtime.capacity_events[-1], ("SHED", 1))
        runtime.close()

    def pattern_runtime(self, delays, residence_ms=5):
        return self.elastic(
            lambda: PatternAdapter(delays), PatternAdapter(delays),
            slow_ms=5, shed_ms=5,
        ) if residence_ms == 50 else ElasticOpportunityRuntime(
            ipc=self.root, host="host", adapters=[PatternAdapter(delays)],
            adapter_factory=lambda: PatternAdapter(delays), maximum_adapters=4,
            slow_offer_ms=5, shed_after_ms=5, evidence_window=8,
            minimum_capacity_residence_ms=residence_ms,
            kinds={"demo.work"}, batch_size=100, idle_ms=1,
            journal=self.root / "mixed.jsonl",
        )

    def test_one_slow_outlier_cannot_inflate_entire_pool(self):
        delays = [30] + [0] * 31
        self.accept(len(delays))
        runtime = self.pattern_runtime(delays)
        runtime.drain(len(delays))
        peak = max([1, *(capacity for event, capacity in runtime.capacity_events
                        if event == "GROW")])
        # It may finish before a later visit observes the threshold; either one
        # or the single escape lane is valid, but a lone outlier cannot do more.
        self.assertLessEqual(peak, 2)
        runtime.close()

    def test_clustered_slow_work_grows_and_trailing_cheap_work_sheds(self):
        delays = [0] * 12 + [30] * 12 + [0] * 24
        self.accept(len(delays))
        runtime = self.pattern_runtime(delays)
        runtime.drain(len(delays))
        self.assertIn(("GROW", 4), runtime.capacity_events)
        time.sleep(.006)
        while len(runtime.adapters) > 1:
            runtime.visit()
        self.assertEqual(runtime.capacity_events[-1], ("SHED", 1))
        runtime.close()

    def test_restart_forgets_mixed_latency_evidence(self):
        delays = [30] * 8
        self.accept(8)
        runtime = self.pattern_runtime(delays)
        runtime.drain(8)
        self.assertGreater(len(runtime.adapters), 1)
        runtime.close()
        more = [0] * 4
        start = 8
        for number in range(start, start + len(more)):
            value = package("sender", "host", "demo.work", {"n": number})
            self.porter.deposit(value)
        all_delays = delays + more
        restarted = self.pattern_runtime(all_delays)
        self.assertEqual(len(restarted.adapters), 1)
        self.assertEqual(restarted.offer_ms, [])
        restarted.drain(4)
        self.assertEqual(restarted.capacity_events, [])
        restarted.close()

    def test_full_capacity_reaps_without_reenumerating_candidates(self):
        self.accept(20)
        gate = threading.Event()
        runtime = self.elastic(
            lambda: GateAdapter(gate), GateAdapter(gate), maximum=2,
            slow_ms=5, shed_ms=20,
        )
        runtime.visit()
        self.wait_for(lambda: len(runtime.inflight) == 1)
        for _ in range(20):
            runtime.visit()
        self.assertEqual(runtime.inspection_count, 1)
        gate.set()
        runtime.drain(20)
        # Two ten-row snapshots drain the work. A final empty inspection can
        # coincide with reaping the twentieth return in that same visit.
        self.assertLessEqual(runtime.inspection_count, 3)
        runtime.close()

    def test_cached_candidate_is_revalidated_before_offer(self):
        values = self.accept(3)
        gate = threading.Event()
        adapter = GateAdapter(gate)
        runtime = self.elastic(lambda: GateAdapter(), adapter, maximum=1)
        runtime.visit()
        self.wait_for(lambda: len(runtime.inflight) == 1)
        skipped = runtime.candidate_snapshot[0]
        collect_package(self.root, skipped, "other-host")
        gate.set()
        self.assertEqual(runtime.drain(2), 2)
        offered = {value["package"]["package"] for value in adapter.collections}
        self.assertNotIn(skipped, offered)
        runtime.close()

    def test_new_arrival_waits_for_a_later_chosen_inspection(self):
        runtime = ElasticOpportunityRuntime(
            ipc=self.root, host="host", adapters=[GateAdapter()],
            adapter_factory=GateAdapter, maximum_adapters=2,
            slow_offer_ms=5, shed_after_ms=10, inspection_interval_ms=500,
            kinds={"demo.work"}, batch_size=10, idle_ms=1,
            journal=self.root / "arrival.jsonl",
        )
        runtime.visit()
        self.assertEqual(runtime.inspection_count, 1)
        self.accept(1)
        for _ in range(5):
            runtime.visit()
        self.assertEqual(runtime.inspection_count, 1)
        self.assertEqual(runtime.control_returns, 0)
        time.sleep(.51)
        runtime.visit()
        runtime.drain(1)
        self.assertEqual(runtime.control_returns, 1)
        runtime.close()

    def test_serial_publication_overlaps_only_adapter_waits(self):
        self.accept(4)
        gate = threading.Event()
        runtime = BoundedOpportunityRuntime(
            ipc=self.root, host="host", adapters=[GateAdapter(gate) for _ in range(4)],
            max_inflight_offers=4, serial_publication=True,
            kinds={"demo.work"}, batch_size=10, idle_ms=1,
            journal=self.root / "phased.jsonl",
        )
        runtime.visit()
        self.wait_for(lambda: len(runtime.inflight) == 4)
        self.assertEqual(len(list((self.root / "collections" / "facts").glob("CL-*.json"))), 4)
        self.assertEqual(runtime.maximum_opportunities, 4)
        self.assertEqual(runtime.publication_in_progress, 0)
        gate.set(); runtime.drain(4); runtime.close()

    def test_serial_publication_never_overlaps_canonical_transition(self):
        self.accept(4)
        active = 0
        maximum = 0
        lock = threading.Lock()
        original = opportunity_module.collect_package
        def measured(*args, **kwargs):
            nonlocal active, maximum
            with lock:
                active += 1; maximum = max(maximum, active)
            try:
                time.sleep(.01)
                return original(*args, **kwargs)
            finally:
                with lock:
                    active -= 1
        runtime = BoundedOpportunityRuntime(
            ipc=self.root, host="host", adapters=[GateAdapter() for _ in range(4)],
            max_inflight_offers=4, serial_publication=True,
            kinds={"demo.work"}, batch_size=10, idle_ms=1,
            journal=self.root / "serial-publication.jsonl",
        )
        with patch("porter.opportunities.collect_package", measured):
            runtime.visit(); runtime.drain(4)
        self.assertEqual(maximum, 1)
        runtime.close()

    def test_crash_gap_after_cl_has_no_queue_state_and_reoffers_on_restart(self):
        self.accept(1)
        class GapRuntime(BoundedOpportunityRuntime):
            def after_publication(inner, _package_id, _collection):
                raise RuntimeError("lost after CL before offer")
        first_adapter = GateAdapter()
        first = GapRuntime(
            ipc=self.root, host="host", adapters=[first_adapter],
            max_inflight_offers=1, serial_publication=True,
            kinds={"demo.work"}, batch_size=1, idle_ms=1,
            journal=self.root / "gap.jsonl",
        )
        first.visit()
        self.assertEqual(len(list((self.root / "collections" / "facts").glob("CL-*.json"))), 1)
        self.assertEqual(first_adapter.collections, [])
        self.assertEqual(len(list((self.root / "host-runtime" / "dispatch-returned").glob("*.json"))), 0)
        names = {path.name.lower() for path in self.root.glob("**/*") if path.is_file()}
        self.assertFalse(any(word in name for name in names
                             for word in ("queued", "running", "processing", "worker")))
        first.close()

        second_adapter = GateAdapter()
        restarted = BoundedOpportunityRuntime(
            ipc=self.root, host="host", adapters=[second_adapter],
            max_inflight_offers=1, serial_publication=True,
            kinds={"demo.work"}, batch_size=1, idle_ms=1,
            journal=self.root / "restart.jsonl",
        )
        restarted.drain(1)
        self.assertEqual(len(second_adapter.collections), 1)
        self.assertEqual(len(list((self.root / "collections" / "facts").glob("CL-*.json"))), 1)
        restarted.close()


if __name__ == "__main__":
    unittest.main()
