from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from porter.carriage import package_digest
from porter.custody import collect_package, custody
from porter.daemon import Porter
from porter.evidence_identity import EvidenceIdentityRefused, EvidenceKeyHistory, _identity, _sign, key_fact, sign_acceptance, sign_possession, verify_acceptance, verify_possession
from porter.protocol import package
from porter.threshold import generate_private_key, public_key


class BoundedCustodianPluralityExperiment(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(); self.base = Path(self.temporary.name)
        self.value = package("find-me", "harmonicdb", "hdbe.call", {"private_metadata": "visible-to-each-custodian"}, ttl=3600)
        self.porters, self.private, self.history = {}, {}, {}
        for name in ("porter-a", "porter-b", "porter-c"):
            root = self.base / name
            self.porters[name] = Porter("harmonicdb", root, {})
            continuity, evidence = generate_private_key(), generate_private_key()
            fact = key_fact(continuity, name, 0, None, public_key(evidence), activates_at_ms=0, expires_at_ms=2**62)
            self.private[name] = evidence
            self.history[name] = EvidenceKeyHistory(name, public_key(continuity), [fact])

    def tearDown(self): self.temporary.cleanup()

    def accept_and_sign(self, name):
        receipt = self.porters[name].deposit(self.value)
        key = self.history[name].chain[0]
        statement = sign_acceptance(self.base / name, name, self.value["package"], key["evidence_key"], self.private[name], issued_at_ms=receipt["accepted_at_ms"] + 1)
        return receipt, statement

    def verify(self, name, statement):
        return verify_acceptance(statement, self.history[name], expected_recipient="harmonicdb", expected_package=self.value["package"], expected_digest=package_digest(self.value))

    def test_same_host_recipient_has_distinct_attributable_custodians(self):
        statements = {name: self.accept_and_sign(name)[1] for name in ("porter-a", "porter-b")}
        self.assertEqual({"harmonicdb"}, {statement["recipient"] for statement in statements.values()})
        self.assertEqual({"porter-a", "porter-b"}, {statement["custodian"] for statement in statements.values()})
        for name, statement in statements.items(): self.verify(name, statement)
        with self.assertRaises(EvidenceIdentityRefused): self.verify("porter-b", statements["porter-a"])

    def test_original_custodian_can_disappear_and_replacement_preserves_package(self):
        _, a = self.accept_and_sign("porter-a"); _, b = self.accept_and_sign("porter-b")
        self.verify("porter-a", a); self.verify("porter-b", b)
        # Complete loss of A changes neither Package identity nor B's custody.
        for path in sorted((self.base / "porter-a").rglob("*"), key=lambda item: len(item.parts), reverse=True):
            if path.is_file(): path.unlink()
            elif path.is_dir(): path.rmdir()
        _, c = self.accept_and_sign("porter-c")
        self.verify("porter-c", c)
        recovered = collect_package(self.base / "porter-b", self.value["package"], "harmonicdb-host")
        self.assertEqual(self.value["package"], recovered["package"]["package"])
        self.assertEqual("RECIPIENT_PORTER", custody(self.base / "porter-c", self.value["package"])["current_custody"])

    def test_host_chosen_attention_needs_no_sibling_coordination(self):
        for name in ("porter-a", "porter-b", "porter-c"): self.accept_and_sign(name)
        def host_attention():
            return {name: custody(self.base / name, self.value["package"])["current_custody"] for name in self.porters}
        observed = host_attention()
        self.assertEqual({"RECIPIENT_PORTER"}, set(observed.values()))
        for name in self.porters:
            local = "".join(path.read_text(errors="ignore") for path in (self.base / name).rglob("*") if path.is_file())
            self.assertFalse(any(sibling in local for sibling in self.porters if sibling != name))

    def test_fresh_signed_possession_is_testimony_not_dishonest_porter_proof(self):
        receipt, _ = self.accept_and_sign("porter-a"); key = self.history["porter-a"].chain[0]
        honest = sign_possession(self.base / "porter-a", "porter-a", self.value["package"], "nonce-1", key["evidence_key"], self.private["porter-a"], observed_at_ms=receipt["accepted_at_ms"] + 2)
        verify_possession(honest, self.history["porter-a"], expected_recipient="harmonicdb", expected_package=self.value["package"], expected_digest=package_digest(self.value), expected_nonce="nonce-1")
        (self.base / "porter-a" / "inbox" / f"{self.value['package']}.json").unlink()
        with self.assertRaises(EvidenceIdentityRefused):
            sign_possession(self.base / "porter-a", "porter-a", self.value["package"], "nonce-2", key["evidence_key"], self.private["porter-a"], observed_at_ms=receipt["accepted_at_ms"] + 3)
        # A dishonest holder of the same signing key can still assert the shape.
        unsigned = {k: v for k, v in honest.items() if k not in {"statement", "signature"}}
        unsigned["nonce"] = "nonce-2"; unsigned["observed_at_ms"] = receipt["accepted_at_ms"] + 3
        unsigned["statement"] = _identity("SE-", unsigned)
        lie = {**unsigned, "signature": _sign(unsigned, self.private["porter-a"])}
        verify_possession(lie, self.history["porter-a"], expected_recipient="harmonicdb", expected_package=self.value["package"], expected_digest=package_digest(self.value), expected_nonce="nonce-2")

    def test_replication_multiplies_custodian_metadata_exposure(self):
        for name in ("porter-a", "porter-b", "porter-c"): self.accept_and_sign(name)
        exposed = 0
        for name in self.porters:
            stored = json.loads((self.base / name / "inbox" / f"{self.value['package']}.json").read_text())
            exposed += stored["payload"]["private_metadata"] == "visible-to-each-custodian"
        self.assertEqual(3, exposed)


if __name__ == "__main__": unittest.main()
