from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from porter.carriage import accept, package_digest
from porter.custody import collect_package, custody, find_collection, recover_collections
from porter.custody_evidence import CustodyEvidenceRefused, sign_acceptance, verify_acceptance
from porter.lodgement import SimulatedInterruption
from porter.protocol import package
from porter.threshold import generate_private_key, public_key


class ReplicatedCustodyOntologyExperiment(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(); self.base = Path(self.temporary.name)
        self.roots = {name: self.base / name for name in ("a", "b", "c")}
        self.value = package("find-me", "harmonicdb", "hdbe.call", {"one": "correspondence"}, ttl=3600)

    def tearDown(self): self.temporary.cleanup()

    def accept(self, *names):
        return {name: accept(self.roots[name], "harmonicdb", self.value)[0] for name in names}

    def test_acceptance_responsibility_is_custodian_local_and_nonexclusive(self):
        facts = self.accept("a", "b", "c")
        self.assertEqual(3, len({fact["acceptance"] for fact in facts.values()}))
        self.assertEqual({"RECIPIENT_PORTER"}, {custody(self.roots[name], self.value["package"])["current_custody"] for name in facts})
        self.assertEqual({package_digest(self.value)}, {fact["package_digest"] for fact in facts.values()})

    def test_partial_then_redundant_collection_needs_no_global_state(self):
        self.accept("a", "b", "c")
        a = collect_package(self.roots["a"], self.value["package"], "host")
        self.assertEqual("RECIPIENT_HOST", custody(self.roots["a"], self.value["package"])["current_custody"])
        self.assertEqual({"RECIPIENT_PORTER"}, {custody(self.roots[name], self.value["package"])["current_custody"] for name in ("b", "c")})
        b = collect_package(self.roots["b"], self.value["package"], "host")
        self.assertNotEqual(a["collection"], b["collection"])
        self.assertEqual(a["package"], b["package"])
        self.assertEqual("RECIPIENT_PORTER", custody(self.roots["c"], self.value["package"])["current_custody"])

    def test_crash_before_first_cl_can_recover_from_another_custodian(self):
        self.accept("a", "b")
        with self.assertRaises(SimulatedInterruption):
            collect_package(self.roots["a"], self.value["package"], "host", "association_reservation")
        self.assertIsNone(find_collection(self.roots["a"], self.value["package"]))
        b = collect_package(self.roots["b"], self.value["package"], "host")
        self.assertEqual(self.value["package"], b["package"]["package"])
        # A still owns its copy and may later transfer it; this is not new correspondence.
        a = collect_package(self.roots["a"], self.value["package"], "host")
        self.assertNotEqual(a["collection"], b["collection"])

    def test_crash_after_one_cl_recovers_that_local_transfer_without_sibling_knowledge(self):
        self.accept("a", "b")
        with self.assertRaises(SimulatedInterruption):
            collect_package(self.roots["a"], self.value["package"], "host", "collection")
        recovered = recover_collections(self.roots["a"])
        self.assertEqual(1, len(recovered))
        self.assertEqual("RECIPIENT_HOST", custody(self.roots["a"], self.value["package"])["current_custody"])
        self.assertEqual("RECIPIENT_PORTER", custody(self.roots["b"], self.value["package"])["current_custody"])

    def test_late_replica_legitimately_accepts_after_another_collection(self):
        self.accept("a"); collect_package(self.roots["a"], self.value["package"], "host")
        late = self.accept("b")["b"]
        self.assertEqual(self.value["package"], late["package"]["package"])
        self.assertEqual("RECIPIENT_PORTER", custody(self.roots["b"], self.value["package"])["current_custody"])

    def test_disappearance_changes_knowledge_not_historical_facts(self):
        facts = self.accept("a", "b", "c")
        retained = {name: json.loads(json.dumps(fact)) for name, fact in facts.items()}
        # Model loss of B's complete independently operated store.
        for path in sorted(self.roots["b"].rglob("*"), reverse=True):
            if path.is_file(): path.unlink()
            elif path.is_dir(): path.rmdir()
        self.assertEqual("NOT_ACCEPTED_HERE", custody(self.roots["b"], self.value["package"])["current_custody"])
        self.assertEqual(facts["b"]["acceptance"], retained["b"]["acceptance"])
        self.assertEqual("RECIPIENT_PORTER", custody(self.roots["c"], self.value["package"])["current_custody"])

    def test_expiry_does_not_release_post_acceptance_responsibility(self):
        self.value["created"], self.value["expires"] = 1, 2
        # Direct AC fixture models acceptance while valid; Collection itself has no expiry gate.
        self.accept("a")
        fact = collect_package(self.roots["a"], self.value["package"], "host")
        self.assertEqual("COLLECTED", fact["state"])
        self.assertEqual("RECIPIENT_HOST", custody(self.roots["a"], self.value["package"])["current_custody"])

    def test_signed_ac_evidence_is_useful_with_only_one_porter_and_cannot_precede_ac(self):
        private = generate_private_key(); public = public_key(private)
        with self.assertRaisesRegex(CustodyEvidenceRefused, "no canonical"):
            sign_acceptance(self.roots["a"], "harmonicdb", self.value["package"], private)
        acceptance = self.accept("a")["a"]
        statement = sign_acceptance(self.roots["a"], "harmonicdb", self.value["package"], private)
        verified = verify_acceptance(statement, public, expected_porter="harmonicdb", expected_package=self.value["package"], expected_digest=acceptance["package_digest"])
        self.assertEqual(acceptance["acceptance"], verified["acceptance"])
        with self.assertRaises(CustodyEvidenceRefused):
            verify_acceptance(statement, public, expected_porter="another", expected_package=self.value["package"], expected_digest=acceptance["package_digest"])

    def test_signed_ac_remains_testimony_not_present_possession(self):
        private = generate_private_key(); acceptance = self.accept("a")["a"]
        statement = sign_acceptance(self.roots["a"], "harmonicdb", self.value["package"], private)
        (self.roots["a"] / "inbox" / f"{self.value['package']}.json").unlink()
        verify_acceptance(statement, public_key(private), expected_porter="harmonicdb", expected_package=self.value["package"], expected_digest=acceptance["package_digest"])
        self.assertFalse((self.roots["a"] / "inbox" / f"{self.value['package']}.json").exists())


if __name__ == "__main__": unittest.main()
