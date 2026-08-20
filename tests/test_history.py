import json
import tempfile
import unittest
from pathlib import Path

from porter.history import enumerate_candidate_facts


class CanonicalHistoryEnumerationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "acceptances").mkdir()
        (self.root / "collections" / "by-package").mkdir(parents=True)

    def tearDown(self):
        self.temp.cleanup()

    def acceptance(self, number, kind="demo.work"):
        package_id = f"PKG-{number:032x}"
        value = {
            "protocol": "PORTER/1",
            "kind": "REMOTE_ACCEPTANCE",
            "acceptance": f"AC-{number:032x}",
            "recipient": "host",
            "package": {"package": package_id, "kind": kind},
        }
        (self.root / "acceptances" / f"{package_id}.json").write_text(json.dumps(value))
        return package_id

    def test_reads_canonical_ac_minus_cl_without_catalogue_or_stat(self):
        live = self.acceptance(1)
        collected = self.acceptance(2)
        (self.root / "collections" / "by-package" / collected).write_text("CL-2\n")

        values, metrics = enumerate_candidate_facts(self.root, measured=True)

        self.assertEqual(values, [(live, "demo.work")])
        self.assertEqual(metrics["directories_visited"], 2)
        self.assertEqual(metrics["files_opened"], 2)
        self.assertEqual(metrics["json_decodes"], 2)
        self.assertEqual(metrics["cl_association_lookups"], 2)
        self.assertEqual(metrics["path_stat_operations"], 0)
        self.assertEqual(metrics["lock_operations"], 0)

    def test_unknown_files_cannot_invent_history(self):
        package_id = self.acceptance(1)
        (self.root / "acceptances" / "catalogue.sqlite3").write_bytes(b"invented")
        (self.root / "acceptances" / "AC-invented.json").write_text("{}")
        self.assertEqual(enumerate_candidate_facts(self.root), [(package_id, "demo.work")])

    def test_truncated_canonical_fact_fails_closed(self):
        package_id = self.acceptance(1)
        (self.root / "acceptances" / f"{package_id}.json").write_text('{"package":')
        with self.assertRaises(json.JSONDecodeError):
            enumerate_candidate_facts(self.root)

    def test_malformed_canonical_shape_fails_closed(self):
        package_id = self.acceptance(1)
        (self.root / "acceptances" / f"{package_id}.json").write_text('{"package": {}}')
        with self.assertRaisesRegex(ValueError, "malformed canonical acceptance"):
            enumerate_candidate_facts(self.root)


if __name__ == "__main__":
    unittest.main()
