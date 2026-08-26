from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from porter.carriage import accept, package_digest
from porter.custody import collect_package
from porter.evidence_identity import EvidenceIdentityRefused, EvidenceKeyHistory, key_fact, sign_acceptance, sign_possession, verify_acceptance, verify_possession
from porter.protocol import package
from porter.threshold import generate_private_key, public_key


class PorterEvidenceIdentityExperiment(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(); self.root = Path(self.temporary.name)
        self.continuity = generate_private_key(); self.old = generate_private_key(); self.new = generate_private_key()
        self.genesis = key_fact(self.continuity, "porter-a", 0, None, public_key(self.old), activates_at_ms=0, expires_at_ms=200)
        self.successor = key_fact(self.continuity, "porter-a", 1, self.genesis["evidence_key"], public_key(self.new), activates_at_ms=200, expires_at_ms=400)
        self.history = EvidenceKeyHistory("porter-a", public_key(self.continuity), [self.genesis, self.successor])
        self.value = package("sender", "porter-a", "demo.work", {"evidence": True}, ttl=3600)
        self.acceptance, _ = accept(self.root, "porter-a", self.value)
        # Use a controlled historical acceptance time inside the experimental key epochs.
        import json
        path = self.root / "acceptances" / f"{self.value['package']}.json"
        stored = json.loads(path.read_text()); stored["accepted_at_ms"] = 100; path.write_text(json.dumps(stored))
        self.acceptance = stored

    def tearDown(self): self.temporary.cleanup()

    def test_historical_statement_survives_operational_key_rotation(self):
        old = sign_acceptance(self.root, "porter-a", self.value["package"], self.genesis["evidence_key"], self.old, issued_at_ms=150)
        new = sign_acceptance(self.root, "porter-a", self.value["package"], self.successor["evidence_key"], self.new, issued_at_ms=250)
        for statement in (old, new):
            verify_acceptance(statement, self.history, expected_recipient="porter-a", expected_package=self.value["package"], expected_digest=package_digest(self.value))

    def test_compromised_predecessor_cannot_make_current_testimony(self):
        late = sign_acceptance(self.root, "porter-a", self.value["package"], self.genesis["evidence_key"], self.old, issued_at_ms=250)
        with self.assertRaisesRegex(EvidenceIdentityRefused, "not valid"):
            verify_acceptance(late, self.history, expected_recipient="porter-a", expected_package=self.value["package"], expected_digest=package_digest(self.value))

    def test_continuity_forgery_and_authority_equivocation_fail_closed(self):
        attacker = generate_private_key()
        forged = key_fact(attacker, "porter-a", 1, self.genesis["evidence_key"], public_key(self.new), activates_at_ms=200, expires_at_ms=400)
        with self.assertRaisesRegex(EvidenceIdentityRefused, "signature"):
            EvidenceKeyHistory("porter-a", public_key(self.continuity), [self.genesis, forged])
        fork_key = generate_private_key()
        fork = key_fact(self.continuity, "porter-a", 1, self.genesis["evidence_key"], public_key(fork_key), activates_at_ms=200, expires_at_ms=400)
        with self.assertRaisesRegex(EvidenceIdentityRefused, "equivocated"):
            EvidenceKeyHistory("porter-a", public_key(self.continuity), [self.genesis, self.successor, fork])

    def test_gap_overlap_and_disconnected_history_fail_closed(self):
        gap = key_fact(self.continuity, "porter-a", 1, self.genesis["evidence_key"], public_key(self.new), activates_at_ms=201, expires_at_ms=400)
        with self.assertRaisesRegex(EvidenceIdentityRefused, "gap or overlap"):
            EvidenceKeyHistory("porter-a", public_key(self.continuity), [self.genesis, gap])

    def test_statement_cannot_claim_to_precede_canonical_acceptance(self):
        with self.assertRaisesRegex(EvidenceIdentityRefused, "predates"):
            sign_acceptance(self.root, "porter-a", self.value["package"], self.genesis["evidence_key"], self.old, issued_at_ms=99)

    def test_nonce_bound_possession_observation_requires_current_inbox_bytes(self):
        statement = sign_possession(self.root, "porter-a", self.value["package"], "nonce-one", self.genesis["evidence_key"], self.old, observed_at_ms=150)
        verify_possession(statement, self.history, expected_recipient="porter-a", expected_package=self.value["package"], expected_digest=package_digest(self.value), expected_nonce="nonce-one")
        with self.assertRaisesRegex(EvidenceIdentityRefused, "challenge"):
            verify_possession(statement, self.history, expected_recipient="porter-a", expected_package=self.value["package"], expected_digest=package_digest(self.value), expected_nonce="nonce-two")
        (self.root / "inbox" / f"{self.value['package']}.json").unlink()
        with self.assertRaisesRegex(EvidenceIdentityRefused, "current accepted bytes"):
            sign_possession(self.root, "porter-a", self.value["package"], "nonce-two", self.genesis["evidence_key"], self.old, observed_at_ms=160)

    def test_collected_porter_does_not_claim_continued_accepted_custody(self):
        collect_package(self.root, self.value["package"], "host")
        with self.assertRaisesRegex(EvidenceIdentityRefused, "current accepted bytes"):
            sign_possession(self.root, "porter-a", self.value["package"], "nonce", self.genesis["evidence_key"], self.old, observed_at_ms=150)


if __name__ == "__main__": unittest.main()
