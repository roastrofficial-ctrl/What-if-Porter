from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from porter.carriage import accept, acceptance_evidence, package_digest
from porter.protocol import package
from porter.replication import custody_claim, reconcile, record, recover
from porter.threshold import ThresholdRefused, _identity, _sign, generate_private_key, public_key, roster, verify_roster


class ThresholdVersusReplicationExperiment(unittest.TestCase):
    def setUp(self):
        self.old_authority, self.new_authority = generate_private_key(), generate_private_key()
        self.keys = {name: generate_private_key() for name in ("a", "b", "c")}
        self.members = [{"porter": name, "endpoint": f"{name}:7410", "signing_key": public_key(key)} for name, key in self.keys.items()]
        self.roster = roster("harmonicdb", self.members, 2, self.old_authority, effective_from=100)
        self.package = package("find-me", "harmonicdb", "hdbe.call", {"same": "correspondence"}, ttl=3600)
        self.replication = record(self.roster, self.package)

    def claims(self, roots: Path, names=("a", "b", "c")):
        claims, acceptances = [], []
        for name in names:
            acceptance, _ = accept(roots / name, "harmonicdb", self.package)
            receipt = acceptance_evidence(acceptance)
            claims.append(custody_claim(self.roster, self.replication, name, self.package, receipt, self.keys[name]))
            acceptances.append(acceptance)
        return claims, acceptances

    def test_one_exact_package_can_have_three_independent_acceptances(self):
        with tempfile.TemporaryDirectory() as value:
            claims, acceptances = self.claims(Path(value))
        self.assertEqual(1, len({item["package"]["package"] for item in acceptances}))
        self.assertEqual(1, len({item["package_digest"] for item in acceptances}))
        self.assertEqual(3, len({item["acceptance"] for item in acceptances}))
        self.assertEqual("CONFIRMED", reconcile(self.roster, self.replication, claims[:2])["status"])

    def test_replication_has_same_fault_boundary_as_threshold(self):
        with tempfile.TemporaryDirectory() as value:
            claims, _ = self.claims(Path(value))
        self.assertEqual("INSUFFICIENT", reconcile(self.roster, self.replication, claims[:1])["status"])
        self.assertEqual("CONFIRMED", reconcile(self.roster, self.replication, claims[:2])["status"])
        self.assertEqual("CONFLICT", reconcile(self.roster, self.replication, [claims[0], claims[0]])["status"])
        forged = {**claims[0], "porter": "b"}
        with self.assertRaises(ThresholdRefused):
            reconcile(self.roster, self.replication, [forged])

    def test_equivocation_is_replica_evidence_not_consensus(self):
        with tempfile.TemporaryDirectory() as value:
            claims, _ = self.claims(Path(value), ("a", "b"))
        altered = copy.deepcopy(claims[0]); altered["package_digest"] = "sha256:" + "0" * 64
        unsigned = {key: item for key, item in altered.items() if key not in {"claim", "signature"}}
        altered["claim"] = _identity("WC-", unsigned)
        altered["signature"] = _sign({key: item for key, item in altered.items() if key != "signature"}, self.keys["a"])
        fact = reconcile(self.roster, self.replication, [altered, claims[1]])
        self.assertEqual("CONFLICT", fact["status"])
        self.assertEqual([altered["claim"]], fact["conflicts"])

    def test_one_surviving_replica_recovers_exact_correspondence(self):
        with tempfile.TemporaryDirectory() as value:
            claims, _ = self.claims(Path(value), ("a", "b"))
        confirmation = reconcile(self.roster, self.replication, claims)
        recovery = recover(self.replication, "b", self.package, "CL-b")
        self.assertEqual(confirmation["package_digest"], recovery["package_digest"])
        with self.assertRaises(ThresholdRefused):
            recover(self.replication, "b", {**self.package, "payload": {"changed": True}}, "CL-forged")

    def test_total_custody_loss_leaves_only_historical_acceptance_proof(self):
        with tempfile.TemporaryDirectory() as value:
            roots = Path(value); claims, _ = self.claims(roots, ("a", "b"))
        confirmation = reconcile(self.roster, self.replication, claims)
        self.assertEqual("CONFIRMED", confirmation["status"])
        self.assertFalse(any((Path(value) / name / "inbox" / f"{self.package['package']}.json").exists() for name in ("a", "b")))

    def test_roster_change_cannot_reinterpret_pinned_replication(self):
        replacement = roster("harmonicdb", self.members[1:], 2, self.new_authority, effective_from=200)
        with tempfile.TemporaryDirectory() as value:
            claims, _ = self.claims(Path(value), ("a", "b"))
        with self.assertRaises(ThresholdRefused):
            reconcile(replacement, self.replication, claims)

    def test_naive_roster_signatures_do_not_define_standing_succession(self):
        old_late = roster("harmonicdb", self.members, 2, self.old_authority, effective_from=300)
        new = roster("harmonicdb", self.members[1:], 2, self.new_authority, effective_from=200)
        # Both signatures verify. There is no predecessor slot or authority epoch
        # in RS, so RS alone cannot prove which key was current at t=300.
        self.assertIs(old_late, verify_roster(old_late, public_key(self.old_authority)))
        self.assertIs(new, verify_roster(new, public_key(self.new_authority)))
        self.assertNotEqual(old_late["roster"], new["roster"])

    def test_rendezvous_or_custodian_movement_does_not_require_new_correspondence_identity(self):
        with tempfile.TemporaryDirectory() as value:
            first, _ = accept(Path(value) / "old-location", "harmonicdb", self.package)
            moved, _ = accept(Path(value) / "new-location", "harmonicdb", self.package)
        self.assertEqual(first["package"]["package"], moved["package"]["package"])
        self.assertEqual(package_digest(first["package"]), package_digest(moved["package"]))


if __name__ == "__main__":
    unittest.main()
