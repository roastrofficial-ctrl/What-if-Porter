import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from porter.candidates import close, inspect, path_for, publish, rebuild, reconcile
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
        self.assertEqual(
            {path.name for path in (self.root / "candidates").iterdir()},
            {
                "candidates.sqlite3",
                "candidates.sqlite3-wal",
                "candidates.sqlite3-shm",
                ".projection.lock",
            },
        )

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

    def test_live_projection_failure_becomes_detectable_absence_and_chosen_inspection_repairs(self):
        value = package("sender", "host", "demo.work", {})
        with patch("porter.candidates._existing_connection", side_effect=sqlite3.DatabaseError("lost connection")):
            self.porter.deposit(value)
        self.assertTrue((self.root / "acceptances" / f"{value['package']}.json").exists())
        self.assertFalse(path_for(self.root).exists())
        self.assertEqual(self.runtime().candidates(), [value["package"]])

    def test_partial_power_loss_approximation_is_rebuilt_before_restarted_porter_is_usable(self):
        values = [self.deposit() for _ in range(2)]
        close(self.root)
        database = path_for(self.root)
        snapshot = database.read_bytes()
        values.extend(self.deposit() for _ in range(3))
        close(self.root)
        database.write_bytes(snapshot)
        self.assertEqual(len(inspect(self.root, {"demo.work"}, 10)), 2)
        Porter("host", self.root, {})
        self.assertEqual(
            {package_id for package_id, _kind in inspect(self.root, {"demo.work"}, 10)},
            {value["package"] for value in values},
        )

    def test_host_restart_does_not_rebuild_complete_warm_porter_projection(self):
        values = [self.deposit() for _ in range(5)]
        first = self.runtime().candidates()
        second = self.runtime().candidates()
        self.assertEqual(first, second)
        self.assertEqual(set(second), {value["package"] for value in values})

    def test_many_stale_rows_cannot_hide_one_live_candidate(self):
        stale = [self.deposit() for _ in range(20)]
        for value in stale:
            collect_package(self.root, value["package"], "host")
            publish(self.root, value)
        live = self.deposit()
        self.assertIn(live["package"], self.runtime().candidates())

    def test_abrupt_process_loss_and_lost_uncheckpointed_wal_tail_cannot_starve_after_porter_restart(self):
        values = [self.deposit() for _ in range(2)]
        close(self.root)
        with patch("porter.carriage.publish", lambda *_: None):
            values.extend(self.deposit() for _ in range(3))
        encoded = json.dumps(
            [{"package": value["package"], "kind": value["kind"]} for value in values[2:]]
        )
        script = (
            "import json,os; from pathlib import Path; "
            "from porter.candidates import publish; "
            f"root=Path({str(self.root)!r}); values=json.loads({encoded!r}); "
            "[publish(root,value) for value in values]; os._exit(0)"
        )
        environment = dict(os.environ)
        environment["PYTHONPATH"] = str(Path(__file__).parents[1])
        subprocess.run([sys.executable, "-c", script], env=environment, check=True)
        database = path_for(self.root)
        self.assertTrue(database.with_name(database.name + "-wal").exists())
        database.with_name(database.name + "-wal").unlink()
        database.with_name(database.name + "-shm").unlink(missing_ok=True)
        self.assertEqual(len(inspect(self.root, {"demo.work"}, 10)), 2)
        Porter("host", self.root, {})
        self.assertEqual(
            {package_id for package_id, _kind in inspect(self.root, {"demo.work"}, 10)},
            {value["package"] for value in values},
        )


if __name__ == "__main__":
    unittest.main()
