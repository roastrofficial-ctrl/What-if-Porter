import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from porter.daemon import Porter
from porter.host_runtime import Adapter, HostRuntime
from porter.protocol import package
import porter.host_runtime as host_runtime


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

    def test_adapter_output_cannot_change_host_attention_cadence(self):
        self.accept(1)
        adapter = RecordingAdapter()
        original = adapter.dispatch
        def dispatch(dispatch_id, collection):
            value = original(dispatch_id, collection)
            value["next_visit_ms"] = 7
            return value
        adapter.dispatch = dispatch
        runtime = HostRuntime(
            ipc=self.ipc,
            host="host",
            adapter=adapter,
            kinds={"demo.work"},
            batch_size=10,
            idle_ms=100,
            journal=self.ipc / "runtime.jsonl",
        )
        runtime.visit()
        self.assertEqual(runtime.idle_ms, 100)

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

    def test_crash_after_cl_before_adapter_leaves_recoverable_host_custody(self):
        value = self.accept(1)[0]
        original = host_runtime.append_json
        def crash(path, observation):
            if observation.get("observation") == "DISPATCH_BEGAN":
                raise RuntimeError("crash after CL before adapter")
            return original(path, observation)
        adapter = RecordingAdapter()
        with patch.object(host_runtime, "append_json", crash):
            with self.assertRaisesRegex(RuntimeError, "after CL"):
                self.runtime(adapter).visit()
        self.assertEqual(adapter.collections, [])
        self.assertTrue((self.ipc / "collections" / "by-package" / value["package"]).exists())
        restarted = RecordingAdapter()
        self.assertEqual(self.runtime(restarted).visit(), 1)
        self.assertEqual(restarted.collections[0]["package"]["package"], value["package"])

    def test_batch_crash_has_no_batch_rollback(self):
        values = self.accept(10)
        class CrashAfterFour(RecordingAdapter):
            def dispatch(inner, dispatch_id, collection):
                if len(inner.collections) == 4:
                    raise RuntimeError("fifth dispatch crashed")
                return super(CrashAfterFour, inner).dispatch(dispatch_id, collection)
        with self.assertRaisesRegex(RuntimeError, "fifth"):
            self.runtime(CrashAfterFour(), batch=10).visit()
        self.assertEqual(len(list((self.ipc / "collections" / "facts").glob("CL-*.json"))), 5)
        self.assertEqual(len(list((self.ipc / "host-runtime" / "dispatch-returned").glob("*.json"))), 4)
        self.assertEqual(len(list((self.ipc / "inbox").glob("PKG-*.json"))), 5)
        restarted = RecordingAdapter()
        self.assertEqual(self.runtime(restarted, batch=10).visit(), 6)
        delivered = {fact["package"]["package"] for fact in restarted.collections}
        self.assertEqual(len(delivered), 6)
        self.assertTrue(delivered <= {value["package"] for value in values})

    def test_runtime_absence_cannot_collect_or_invoke(self):
        value = self.accept(1)[0]
        self.assertFalse((self.ipc / "collections" / "by-package" / value["package"]).exists())
        self.assertFalse((self.ipc / "host-runtime").exists())
        adapter = RecordingAdapter()
        self.assertEqual(self.runtime(adapter).visit(), 1)
        self.assertEqual(len(adapter.collections), 1)

    def test_runtime_recovery_earns_direct_collection_lookup(self):
        self.accept(3)
        adapter = RecordingAdapter()
        from porter.custody import _facts
        with patch("porter.custody._facts", wraps=_facts) as facts:
            self.assertEqual(self.runtime(adapter).visit(), 3)
        self.assertEqual(facts.call_count, 1, "Collection rescanned CL history after recovery")

    def test_telemetry_deletion_changes_no_porter_or_application_truth(self):
        value = self.accept(1)[0]
        adapter = RecordingAdapter()
        self.runtime(adapter).visit()
        acceptance = (self.ipc / "acceptances" / f"{value['package']}.json").read_bytes()
        collection = next((self.ipc / "collections" / "facts").glob("CL-*.json")).read_bytes()
        (self.ipc / "runtime.jsonl").unlink()
        self.assertEqual((self.ipc / "acceptances" / f"{value['package']}.json").read_bytes(), acceptance)
        self.assertEqual(next((self.ipc / "collections" / "facts").glob("CL-*.json")).read_bytes(), collection)

    def test_malformed_adapter_control_cannot_manufacture_runtime_state(self):
        value = self.accept(1)[0]
        script = Path(__file__).parents[1] / "examples" / "adversarial_adapter.py"
        with patch.dict(os.environ, {"ADVERSARIAL_ADAPTER": "malformed"}):
            adapter = Adapter(f"{sys.executable} {script}")
            try:
                with self.assertRaisesRegex(RuntimeError, "invalid.*control reply"):
                    self.runtime(adapter).visit()
            finally:
                adapter.close()
        self.assertTrue((self.ipc / "collections" / "by-package" / value["package"]).exists())
        self.assertFalse((self.ipc / "host-runtime" / "dispatch-returned" / f"{value['package']}.json").exists())

    def test_oversized_adapter_control_is_bounded_and_nonsemantic(self):
        value = self.accept(1)[0]
        script = Path(__file__).parents[1] / "examples" / "adversarial_adapter.py"
        with patch.dict(os.environ, {"ADVERSARIAL_ADAPTER": "huge"}):
            adapter = Adapter(f"{sys.executable} {script}")
            try:
                with self.assertRaisesRegex(RuntimeError, "exceeds limit"):
                    self.runtime(adapter).visit()
            finally:
                adapter.close()
        self.assertTrue((self.ipc / "collections" / "by-package" / value["package"]).exists())
        self.assertFalse((self.ipc / "host-runtime" / "dispatch-returned" / f"{value['package']}.json").exists())

    def test_third_host_uses_unchanged_contract_and_never_returning_is_complete_silence(self):
        value = self.accept(1)[0]
        state = self.ipc / "tiny-state"
        command = f"{sys.executable} {Path(__file__).parents[1] / 'examples' / 'tiny_host_adapter.py'}"
        with patch.dict(os.environ, {
            "PORTER_IPC": str(self.ipc), "TINY_HOST_STATE": str(state)
        }):
            adapter = Adapter(command)
            try:
                self.assertEqual(self.runtime(adapter).visit(), 1)
            finally:
                adapter.close()
        fact = json.loads((state / f"{value['package']}.json").read_text())
        self.assertEqual(fact["application"], "TINY-TRANSFORM/1")
        self.assertEqual(list((self.ipc / "tickets").glob("CT-*.json")), [])

    def test_third_host_may_return_in_later_execution(self):
        value = self.accept(1)[0]
        state = self.ipc / "tiny-state"
        script = Path(__file__).parents[1] / "examples" / "tiny_host_adapter.py"
        environment = {
            "PORTER_IPC": str(self.ipc), "TINY_HOST_STATE": str(state),
            "TINY_HOST_DEFER_RETURN": "1", "TINY_HOST_RECIPIENT": "sender",
        }
        with patch.dict(os.environ, environment):
            adapter = Adapter(f"{sys.executable} {script}")
            try:
                self.assertEqual(self.runtime(adapter).visit(), 1)
            finally:
                adapter.close()
        self.assertEqual(list((self.ipc / "tickets").glob("CT-*.json")), [])
        subprocess.run(
            [sys.executable, str(script), "--release-related"],
            env={**os.environ, **environment}, check=True,
        )
        outbound = json.loads(next((self.ipc / "outgoing").glob("PKG-*.json")).read_text())
        self.assertEqual(outbound["in_reply_to"], value["package"])
        ticket = json.loads(next((self.ipc / "tickets").glob("CT-*.json")).read_text())
        self.assertEqual(ticket["package"], outbound["package"])

    def test_third_host_may_lodge_unrelated_correspondence_later(self):
        value = self.accept(1)[0]
        state = self.ipc / "tiny-state"
        script = Path(__file__).parents[1] / "examples" / "tiny_host_adapter.py"
        environment = {
            "PORTER_IPC": str(self.ipc), "TINY_HOST_STATE": str(state),
            "TINY_HOST_DEFER_RETURN": "1", "TINY_HOST_RECIPIENT": "sender",
        }
        with patch.dict(os.environ, environment):
            adapter = Adapter(f"{sys.executable} {script}")
            try:
                self.runtime(adapter).visit()
            finally:
                adapter.close()
        subprocess.run(
            [sys.executable, str(script), "--release-unrelated"],
            env={**os.environ, **environment}, check=True,
        )
        outbound = json.loads(next((self.ipc / "outgoing").glob("PKG-*.json")).read_text())
        self.assertNotIn("in_reply_to", outbound)
        self.assertNotEqual(outbound["package"], value["package"])


if __name__ == "__main__":
    unittest.main()
