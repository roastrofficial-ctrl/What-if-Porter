import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from porter.candidates import inspect, path_for, publish, rebuild, reconcile
from porter.custody import collect_package
from porter.daemon import Porter
from porter.host_runtime import HostRuntime
from porter.protocol import package


class NoAdapter:
    def close(self):
        pass


class CandidateProjectionTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.porter = Porter("host", self.root, {})

    def tearDown(self):
        self.temp.cleanup()

    def deposit(self, kind="demo.work"):
        value = package("sender", "host", kind, {"meaning": "opaque"})
        self.porter.deposit(value)
        return value

    def runtime(self, kinds={"demo.work"}):
        value = HostRuntime(self.root, "host", NoAdapter(), kinds, 10, 100, self.root / "runtime.jsonl")
        value.recovering = False
        return value

    def test_acceptance_publishes_one_compact_candidate_and_collection_settles_it(self):
        value = self.deposit()
        self.assertEqual(inspect(self.root, {"demo.work"}, 10), [(value["package"], "demo.work")])
        collect_package(self.root, value["package"], "host")
        self.assertEqual(inspect(self.root, {"demo.work"}, 10), [])
        self.assertEqual(len(list((self.root / "candidates").iterdir())), 1)

    def test_missing_projection_rebuilds_only_from_uncollected_acceptance_truth(self):
        held = self.deposit()
        collected = self.deposit()
        collect_package(self.root, collected["package"], "host")
        path_for(self.root).unlink()
        self.assertEqual(inspect(self.root, {"demo.work"}, 10), [(held["package"], "demo.work")])

    def test_malformed_projection_rebuilds_without_changing_canonical_truth(self):
        value = self.deposit()
        path_for(self.root).write_bytes(b"not a database")
        self.assertEqual(inspect(self.root, {"demo.work"}, 10), [(value["package"], "demo.work")])
        self.assertTrue((self.root / "acceptances" / f"{value['package']}.json").exists())

    def test_stale_projection_schema_rebuilds(self):
        value = self.deposit()
        connection = sqlite3.connect(path_for(self.root))
        connection.execute("UPDATE metadata SET value='PORTER-CANDIDATES/0' WHERE name='schema'")
        connection.commit()
        connection.close()
        self.assertEqual(inspect(self.root, {"demo.work"}, 10), [(value["package"], "demo.work")])

    def test_unknown_and_wrong_kind_rows_are_harmless_and_removed_by_runtime(self):
        value = self.deposit("other.work")
        publish(self.root, {"package": "PKG-" + "f" * 32, "kind": "demo.work"})
        connection = sqlite3.connect(path_for(self.root))
        connection.execute("UPDATE candidates SET kind='demo.work' WHERE package=?", (value["package"],))
        connection.commit()
        connection.close()
        self.assertEqual(self.runtime().candidates(), [])
        self.assertEqual(inspect(self.root, {"demo.work"}, 10), [])

    def test_duplicate_row_is_impossible_and_explicit_reconciliation_repairs_missing_row(self):
        value = self.deposit()
        publish(self.root, value)
        connection = sqlite3.connect(path_for(self.root))
        count = connection.execute("SELECT count(*) FROM candidates WHERE package=?", (value["package"],)).fetchone()[0]
        connection.execute("DELETE FROM candidates WHERE package=?", (value["package"],))
        connection.commit()
        connection.close()
        self.assertEqual(count, 1)
        result = reconcile(self.root)
        self.assertTrue(result["repaired"])
        self.assertEqual(result["missing"], 1)

    def test_crash_after_ac_before_projection_is_repaired_on_porter_restart(self):
        value = package("sender", "host", "demo.work", {})
        with self.assertRaisesRegex(RuntimeError, "durable remote acceptance"):
            self.porter.deposit(value, fail_after="acceptance")
        self.assertTrue((self.root / "acceptances" / f"{value['package']}.json").exists())
        self.assertEqual(inspect(self.root, {"demo.work"}, 10), [])
        Porter("host", self.root, {})
        self.assertEqual(inspect(self.root, {"demo.work"}, 10), [(value["package"], "demo.work")])

    def test_crash_after_candidate_publication_changes_no_canonical_meaning(self):
        value = package("sender", "host", "demo.work", {})
        with self.assertRaisesRegex(RuntimeError, "candidate projection"):
            self.porter.deposit(value, fail_after="candidate")
        self.assertEqual(inspect(self.root, {"demo.work"}, 10), [(value["package"], "demo.work")])
        self.assertFalse((self.root / "collections" / "by-package" / value["package"]).exists())

    def test_crash_after_cl_before_candidate_removal_leaves_harmless_recoverable_stale_row(self):
        value = self.deposit()
        with self.assertRaisesRegex(RuntimeError, "collection"):
            collect_package(self.root, value["package"], "host", fail_after="collection")
        self.assertEqual(inspect(self.root, {"demo.work"}, 10), [(value["package"], "demo.work")])
        Porter("host", self.root, {})
        self.assertEqual(inspect(self.root, {"demo.work"}, 10), [])

    def test_crash_after_candidate_removal_preserves_collection_truth(self):
        value = self.deposit()
        with self.assertRaisesRegex(RuntimeError, "candidate_removal"):
            collect_package(self.root, value["package"], "host", fail_after="candidate_removal")
        self.assertEqual(inspect(self.root, {"demo.work"}, 10), [])
        fact = next((self.root / "collections" / "facts").glob("CL-*.json"))
        self.assertEqual(json.loads(fact.read_text())["package"]["package"], value["package"])

    def test_candidate_settled_between_inspection_and_collection_cannot_create_second_cl(self):
        value = self.deposit()
        self.assertEqual(self.runtime().candidates(), [value["package"]])
        first = collect_package(self.root, value["package"], "host")
        second = collect_package(self.root, value["package"], "host")
        self.assertEqual(second["state"], "ALREADY_COLLECTED")
        self.assertEqual(second["collection"], first["collection"])
        self.assertEqual(len(list((self.root / "collections" / "facts").glob("CL-*.json"))), 1)


if __name__ == "__main__":
    unittest.main()
