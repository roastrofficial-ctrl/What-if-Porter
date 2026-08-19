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


if __name__ == "__main__":
    unittest.main()
