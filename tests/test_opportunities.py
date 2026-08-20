import threading
import time
import tempfile
import unittest
from pathlib import Path

from porter.daemon import Porter
from porter.host_runtime import HostRuntime
from porter.opportunities import BoundedOpportunityRuntime
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


if __name__ == "__main__":
    unittest.main()
