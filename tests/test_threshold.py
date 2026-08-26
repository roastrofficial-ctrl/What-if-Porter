from __future__ import annotations

import copy
import unittest

from porter.carriage import acceptance_evidence, accept, package_digest
from porter.threshold import ThresholdRefused, custody_claim, draft, generate_private_key, public_key, reconcile, roster, verify_roster


class ThresholdExperiment(unittest.TestCase):
    def setUp(self):
        self.standing = generate_private_key()
        self.keys = {name: generate_private_key() for name in ("a", "b", "c")}
        members = [{"porter": name, "endpoint": f"{name}.example:7410", "signing_key": public_key(key)} for name, key in self.keys.items()]
        self.roster = roster("harmonicdb", members, 2, self.standing, effective_from=100)
        self.deposit, self.packages = draft(self.roster, "find-me", "hdbe.call", {"x": 1}, created=200)

    def claims(self, temporary, names=("a", "b", "c")):
        results = []
        for index, name in enumerate(("a", "b", "c")):
            if name not in names:
                continue
            acceptance, _ = accept(temporary / name, "harmonicdb", self.packages[index])
            receipt = acceptance_evidence(acceptance)
            results.append(custody_claim(self.roster, self.deposit, name, self.packages[index], receipt, self.keys[name]))
        return results

    def test_signed_roster_and_two_distinct_members_confirm(self):
        import tempfile
        from pathlib import Path
        verify_roster(self.roster, public_key(self.standing))
        with tempfile.TemporaryDirectory() as value:
            fact = reconcile(self.roster, self.deposit, self.claims(Path(value), ("a", "b")), observed_at=300)
        self.assertEqual("CONFIRMED", fact["status"])
        self.assertEqual(["a", "b"], fact["corroborated_by"])

    def test_one_member_cannot_masquerade_as_two_or_repeat_its_vote(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as value:
            claims = self.claims(Path(value), ("a",))
        self.assertEqual("INSUFFICIENT", reconcile(self.roster, self.deposit, claims)["status"])
        self.assertEqual("CONFLICT", reconcile(self.roster, self.deposit, claims * 2)["status"])
        forged = {**claims[0], "porter": "b"}
        with self.assertRaises(ThresholdRefused):
            reconcile(self.roster, self.deposit, [forged])

    def test_constituent_package_digests_differ_but_logical_digest_is_shared(self):
        self.assertEqual(3, len({package_digest(value) for value in self.packages}))
        self.assertEqual(1, len({value["payload"]["threshold"]["logical_digest"] for value in self.packages}))

    def test_signed_equivocation_is_retained_as_conflict(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as value:
            claims = self.claims(Path(value), ("a", "b"))
        altered = copy.deepcopy(claims[0]); altered["logical_digest"] = "sha256:" + "0" * 64
        unsigned = {key: item for key, item in altered.items() if key not in {"claim", "signature"}}
        from porter.threshold import _identity, _sign
        altered["claim"] = _identity("WC-", unsigned)
        altered["signature"] = _sign({key: item for key, item in altered.items() if key != "signature"}, self.keys["a"])
        fact = reconcile(self.roster, self.deposit, [altered, claims[1]])
        self.assertEqual("CONFLICT", fact["status"])
        self.assertEqual([altered["claim"]], fact["conflicts"])

    def test_deposit_pins_old_roster_across_rotation(self):
        rotated = roster("harmonicdb", self.roster["members"][1:], 2, self.standing, effective_from=250)
        self.assertNotEqual(rotated["roster"], self.deposit["roster"])
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as value:
            old_claims = self.claims(Path(value), ("a", "b"))
        with self.assertRaises(ThresholdRefused):
            reconcile(rotated, self.deposit, old_claims)

    def test_confirmation_is_historical_not_proof_of_current_retrievability(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as value:
            claims = self.claims(Path(value), ("a", "b"))
        fact = reconcile(self.roster, self.deposit, claims)
        self.assertEqual("CONFIRMED", fact["status"])
        # Both members can later withhold or disappear; TC has no current-state oracle.
        available_members = set()
        self.assertFalse(available_members & set(fact["corroborated_by"]))


if __name__ == "__main__":
    unittest.main()
