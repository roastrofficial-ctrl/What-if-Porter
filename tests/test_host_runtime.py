import json
import tempfile
import unittest
from pathlib import Path

from porter.daemon import Porter
from porter.host_runtime import HostRuntime
from porter.protocol import package


class RecordingAdapter:
    def __init__(self):
        self.collections = []

    def dispatch(self, dispatch_id, collection):
        self.collections.append(collection)
        return {
            "contract": "PORTER-HOST-ADAPTER/1",
            "dispatch": dispatch_id,
            "runtime_observation": "ADAPTER_RETURNED_CONTROL",
        }

    def close(self):
        pass


class PolicyAdapter(RecordingAdapter):
    def dispatch(self, dispatch_id, collection):
        value = super().dispatch(dispatch_id, collection)
        value["next_visit_ms"] = 7
        return value


class CrashOnSecondAdapter(RecordingAdapter):
    def dispatch(self, dispatch_id, collection):
        if len(self.collections) == 1:
            raise RuntimeError("application adapter crashed mid-batch")
        return super().dispatch(dispatch_id, collection)


class StopAfterOneAdapter(RecordingAdapter):
    def dispatch(self, dispatch_id, collection):
        value = super().dispatch(dispatch_id, collection)
        self.runtime.stop()
        return value


class HostRuntimeExperiment(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.ipc = Path(self.temp.name)
        self.porter = Porter("host", self.ipc, {})

    def tearDown(self):
        self.temp.cleanup()

    def runtime(self, adapter, batch=10):
        return HostRuntime(
            ipc=self.ipc,
            host="host",
            adapter=adapter,
            kinds={"demo.work"},
            batch_size=batch,
            idle_ms=100,
            journal=self.ipc / "runtime.jsonl",
        )

    def accept(self, count, kind="demo.work"):
        values = [package("sender", "host", kind, {"n": n}) for n in range(count)]
        for value in values:
            self.porter.deposit(value)
        return values

    def test_runtime_collects_bounded_batch_and_hands_facts_to_adapter(self):
        values = self.accept(3)
        adapter = RecordingAdapter()
        runtime = self.runtime(adapter, batch=2)
        self.assertEqual(runtime.visit(), 2)
        self.assertEqual(len(adapter.collections), 2)
        self.assertTrue(all(value["kind"] == "COLLECTION" for value in adapter.collections))
        self.assertEqual(len(list((self.ipc / "inbox").glob("PKG-*.json"))), 1)
        self.assertEqual(runtime.visit(), 1)
        self.assertEqual({fact["package"]["package"] for fact in adapter.collections}, {value["package"] for value in values})

    def test_returned_control_is_operational_not_application_disposition(self):
        value = self.accept(1)[0]
        runtime = self.runtime(RecordingAdapter())
        runtime.visit()
        observation = json.loads((self.ipc / "host-runtime" / "dispatch-returned" / f"{value['package']}.json").read_text())
        self.assertEqual(observation["runtime_observation"], "ADAPTER_RETURNED_CONTROL")
        self.assertNotIn("processed", observation)
        self.assertNotIn("completed", observation)
        self.assertNotIn("failed", observation)
        self.assertEqual(runtime.visit(), 0)

    def test_runtime_policy_filters_without_interpreting_payload(self):
        self.accept(1, "other.work")
        adapter = RecordingAdapter()
        self.assertEqual(self.runtime(adapter).visit(), 0)
        self.assertEqual(adapter.collections, [])

    def test_application_policy_may_change_attention_within_runtime_limits(self):
        self.accept(1)
        adapter = PolicyAdapter()
        runtime = HostRuntime(
            ipc=self.ipc,
            host="host",
            adapter=adapter,
            kinds={"demo.work"},
            batch_size=10,
            idle_ms=100,
            journal=self.ipc / "runtime.jsonl",
            min_idle_ms=10,
            max_idle_ms=1000,
        )
        runtime.visit()
        self.assertEqual(runtime.idle_ms, 10)

    def test_restart_mid_batch_redelivers_only_ambiguous_and_unvisited_work(self):
        values = self.accept(3)
        crashing = CrashOnSecondAdapter()
        runtime = self.runtime(crashing)
        with self.assertRaisesRegex(RuntimeError, "mid-batch"):
            runtime.visit()
        returned = self.ipc / "host-runtime" / "dispatch-returned"
        self.assertEqual(len(list(returned.glob("*.json"))), 1)
        returned_before_restart = next(returned.glob("*.json")).stem
        restarted = RecordingAdapter()
        self.assertEqual(self.runtime(restarted).visit(), 2)
        redelivered = {fact["package"]["package"] for fact in restarted.collections}
        self.assertEqual(len(redelivered), 2)
        self.assertEqual(redelivered | {returned_before_restart}, {value["package"] for value in values})

    def test_host_chosen_shutdown_stops_between_dispatches_without_losing_custody(self):
        values = self.accept(3)
        adapter = StopAfterOneAdapter()
        runtime = self.runtime(adapter)
        adapter.runtime = runtime
        self.assertEqual(runtime.visit(), 1)
        restarted = RecordingAdapter()
        self.assertEqual(self.runtime(restarted).visit(), 2)
        observed = {adapter.collections[0]["package"]["package"]}
        observed.update(fact["package"]["package"] for fact in restarted.collections)
        self.assertEqual(observed, {value["package"] for value in values})


if __name__ == "__main__":
    unittest.main()
