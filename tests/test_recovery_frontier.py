import json
import tempfile
import threading
import unittest
from pathlib import Path

from porter.custody import collect_package, recover_collections_for_runtime
from porter.daemon import Porter
from porter.protocol import package


class RecoveryFrontierTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.porter = Porter("host", self.root, {})

    def tearDown(self):
        self.temp.cleanup()

    def collect(self, count, start=0):
        values = []
        for number in range(start, start + count):
            value = package("sender", "host", "demo.work", {"n": number})
            self.porter.deposit(value)
            collect_package(self.root, value["package"], "host")
            values.append(value)
        return values

    def test_clean_warm_audit_parses_no_canonical_facts(self):
        self.collect(20)
        (self.root / "collections" / "recovery" / "frontier.json").unlink(
            missing_ok=True
        )
        cold = recover_collections_for_runtime(self.root)
        warm = recover_collections_for_runtime(self.root)
        self.assertEqual((cold["mode"], cold["parsed_facts"]),
                         ("FULL_RECONSTRUCTION", 20))
        self.assertEqual((warm["mode"], warm["parsed_facts"], warm["audited_facts"]),
                         ("WARM_AUDIT", 0, 20))

    def test_exact_extension_parses_only_new_facts(self):
        self.collect(10)
        recover_collections_for_runtime(self.root)
        self.collect(2, start=10)
        value = recover_collections_for_runtime(self.root)
        self.assertEqual(value["mode"], "EXACT_EXTENSION")
        self.assertEqual(value["parsed_facts"], 2)
        self.assertEqual(len(value["collections"]), 12)

    def test_missing_projection_forces_full_reconstruction_and_repairs(self):
        values = self.collect(8)
        recover_collections_for_runtime(self.root)
        missing = self.root / "collected" / f"{values[3]['package']}.json"
        missing.unlink()
        value = recover_collections_for_runtime(self.root)
        self.assertEqual((value["mode"], value["parsed_facts"]),
                         ("FULL_RECONSTRUCTION", 8))
        self.assertTrue(missing.exists())

    def test_changed_fact_or_association_invalidates_frontier(self):
        values = self.collect(6)
        recover_collections_for_runtime(self.root)
        package_id = values[0]["package"]
        association = self.root / "collections" / "by-package" / package_id
        association.write_text("CL-bogus\n")
        value = recover_collections_for_runtime(self.root)
        self.assertEqual(value["mode"], "FULL_RECONSTRUCTION")
        self.assertEqual(value["parsed_facts"], 6)
        self.assertNotEqual(association.read_text().strip(), "CL-bogus")

        fact = next((self.root / "collections" / "facts").glob("CL-*.json"))
        canonical = json.loads(fact.read_text())
        fact.write_text(json.dumps(canonical, indent=2))
        value = recover_collections_for_runtime(self.root)
        self.assertEqual((value["mode"], value["parsed_facts"]),
                         ("FULL_RECONSTRUCTION", 6))

    def test_missing_or_corrupt_frontier_forces_complete_reconstruction(self):
        self.collect(5)
        recover_collections_for_runtime(self.root)
        frontier = self.root / "collections" / "recovery" / "frontier.json"
        frontier.write_text("not-json")
        corrupt = recover_collections_for_runtime(self.root)
        self.assertEqual((corrupt["mode"], corrupt["parsed_facts"]),
                         ("FULL_RECONSTRUCTION", 5))
        frontier.unlink()
        missing = recover_collections_for_runtime(self.root)
        self.assertEqual((missing["mode"], missing["parsed_facts"]),
                         ("FULL_RECONSTRUCTION", 5))

    def test_missing_old_canonical_fact_invalidates_frontier(self):
        self.collect(5)
        recover_collections_for_runtime(self.root)
        next((self.root / "collections" / "facts").glob("CL-*.json")).unlink()
        value = recover_collections_for_runtime(self.root)
        self.assertEqual((value["mode"], value["parsed_facts"]),
                         ("FULL_RECONSTRUCTION", 4))

    def test_competing_recovery_serialises_disposable_frontier(self):
        self.collect(20)
        results = []
        threads = [threading.Thread(
            target=lambda: results.append(recover_collections_for_runtime(self.root))
        ) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(sorted(value["parsed_facts"] for value in results), [0, 20])
        self.assertEqual(len(json.loads(
            (self.root / "collections" / "recovery" / "frontier.json").read_text()
        )["facts"]), 20)


if __name__ == "__main__":
    unittest.main()
