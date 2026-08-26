from __future__ import annotations

import copy
import tempfile
import time
import unittest
from pathlib import Path

from porter.authority import AuthorityStore, authority_root, derive, generate_keypair, transition
from porter.authorization import (
    AuthorizationRefused,
    authorization_key_id,
    evaluate_admission,
    sign_package,
    verify_package,
)
from porter.carriage import package_digest
from porter.introduction import proof, verify_proof
from porter.protocol import package


NOW = int(time.time())


class CorrespondenceAuthorizationExperiment(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.authority_private, authority_public = generate_keypair()
        self.k0_private, self.k0_public = generate_keypair()
        self.k1_private, self.k1_public = generate_keypair()
        self.terms0 = self.terms(self.k0_public, 0)
        self.terms1 = self.terms(self.k1_public, 1)
        self.root = authority_root(
            "signing-host-authority",
            authority_public,
            "signing-host",
            "find-me",
            "IN-P0",
            self.terms0,
        )
        self.k0 = authorization_key_id(self.k0_public, 0, "find-me", "signing-host")
        self.k1 = authorization_key_id(self.k1_public, 1, "find-me", "signing-host")

    def tearDown(self):
        self.temporary.cleanup()

    def terms(self, public_key: str, generation: int, **changes) -> dict:
        value = {
            "kinds": ["signing.request"],
            "max_package_bytes": 16384,
            "max_outstanding_packages": 10,
            "max_outstanding_bytes": 1048576,
            "expires_at": NOW + 86400,
            "authorization_public_key": public_key,
            "authorization_generation": generation,
        }
        value.update(changes)
        return value

    def pkg(self, marker: str, **changes) -> dict:
        value = package(
            "find-me",
            "signing-host",
            "signing.request",
            {"marker": marker},
            ttl=3600,
        )
        value.update(changes)
        return value

    def authorize(self, value: dict, *, private: str | None = None, introduction: str = "IN-P0", key: str | None = None, generation: int = 0) -> dict:
        return sign_package(
            private or self.k0_private,
            value,
            root=self.root["root"],
            introduction=introduction,
            authorization_key=key or self.k0,
            authorization_generation=generation,
        )

    def current0(self) -> dict:
        return derive(self.root, [])

    def test_symmetric_verifier_can_manufacture_indistinguishable_sender_proof(self):
        shared = "existing-standing-operational-secret"
        legitimate = self.pkg("legitimate")
        forged = self.pkg("custodian-manufactured")
        self.assertTrue(verify_proof(shared, legitimate, proof(shared, legitimate)))
        self.assertTrue(verify_proof(shared, forged, proof(shared, forged)))
        self.assertNotEqual(proof(shared, legitimate), proof(shared, forged))

    def test_exact_package_and_authority_context_are_bound(self):
        value = self.pkg("exact")
        evidence = self.authorize(value)
        verified = verify_package(value, evidence, self.root, self.current0())
        self.assertEqual("PACKAGE_SIGNATURE_VALID", verified["proof_state"])

        mutations = {
            "payload": {"marker": "changed"},
            "package": "PKG-another",
            "from": "another-sender",
            "to": "another-recipient",
            "kind": "admin.request",
            "reply_to": "another-host",
        }
        for field, replacement in mutations.items():
            with self.subTest(field=field):
                attacked = copy.deepcopy(value)
                attacked[field] = replacement
                with self.assertRaises(AuthorizationRefused):
                    verify_package(attacked, evidence, self.root, self.current0())

        altered = copy.deepcopy(evidence)
        altered["introduction"] = "IN-other"
        with self.assertRaises(AuthorizationRefused):
            verify_package(value, altered, self.root, self.current0())
        other_root = copy.deepcopy(self.root)
        other_root["root"] = "AR-other"
        with self.assertRaises(AuthorizationRefused):
            verify_package(value, evidence, other_root, {**self.current0(), "root": "AR-other"})

    def test_compromised_custodian_verifier_cannot_forge_for_fresh_custodian(self):
        legitimate = self.pkg("legitimate")
        evidence = self.authorize(legitimate)
        for name in ("porter-a", "porter-b", "porter-c"):
            result = verify_package(legitimate, evidence, self.root, self.current0())
            self.assertEqual("PACKAGE_SIGNATURE_VALID", result["proof_state"], name)

        attacker_private, _ = generate_keypair()
        forged = self.pkg("forged-by-compromised-a")
        forged_evidence = self.authorize(forged, private=attacker_private)
        with self.assertRaisesRegex(AuthorizationRefused, "signature"):
            verify_package(forged, forged_evidence, self.root, self.current0())

        # A's native key, store, configuration, public root, public sender key,
        # old Packages and proofs add no Ed25519 signing capability for K0.
        self.assertEqual("PACKAGE_SIGNATURE_VALID", verify_package(legitimate, evidence, self.root, self.current0())["proof_state"])

    def test_terms_are_recipient_derived_and_local_limits_are_not_sender_claims(self):
        value = self.pkg("terms")
        evidence = self.authorize(value)
        self.assertEqual(
            "AUTHORIZED_FOR_LOCAL_AC",
            evaluate_admission(value, evidence, self.root, self.current0(), now=NOW)["admission"],
        )
        self.assertEqual(
            "REFUSED_LOCAL_COUNT",
            evaluate_admission(value, evidence, self.root, self.current0(), now=NOW, outstanding_count=10)["admission"],
        )
        forbidden = self.pkg("forbidden", kind="admin.request")
        forbidden_evidence = self.authorize(forbidden)
        result = evaluate_admission(forbidden, forbidden_evidence, self.root, self.current0(), now=NOW)
        self.assertEqual("PACKAGE_SIGNATURE_VALID", result["proof_state"])
        self.assertEqual("REFUSED_KIND", result["admission"])

    def test_succession_rotates_key_without_changing_sender_identity(self):
        change = transition(self.root, self.authority_private, "IN-P0", "IN-P1", self.terms1, "CM-rotate")
        stale = self.current0()
        current = derive(self.root, [change])
        old_package = self.pkg("old-key")
        old_proof = self.authorize(old_package)
        new_package = self.pkg("new-key")
        new_proof = self.authorize(new_package, private=self.k1_private, introduction="IN-P1", key=self.k1, generation=1)

        self.assertEqual("AUTHORIZED_FOR_LOCAL_AC", evaluate_admission(old_package, old_proof, self.root, stale, now=NOW)["admission"])
        self.assertEqual("REFUSED_STALE_AUTHORITY", evaluate_admission(old_package, old_proof, self.root, current, now=NOW)["admission"])
        self.assertEqual("AUTHORIZED_FOR_LOCAL_AC", evaluate_admission(new_package, new_proof, self.root, current, now=NOW)["admission"])
        self.assertEqual("find-me", new_package["from"])

    def test_known_fork_keeps_signature_valid_but_refuses_new_ac_and_preserves_replay(self):
        terms_x = self.terms(self.k1_public, 1)
        fork_x = transition(self.root, self.authority_private, "IN-P0", "IN-X", terms_x, "CM-X")
        other_private, other_public = generate_keypair()
        terms_y = self.terms(other_public, 2)
        fork_y = transition(self.root, self.authority_private, "IN-P0", "IN-Y", terms_y, "CM-Y")
        forked = derive(self.root, [fork_x, fork_y])
        value = self.pkg("fork-x")
        evidence = self.authorize(value, private=self.k1_private, introduction="IN-X", key=self.k1, generation=1)
        result = evaluate_admission(value, evidence, self.root, forked, now=NOW)
        self.assertEqual("PACKAGE_SIGNATURE_VALID", result["proof_state"])
        self.assertEqual("FORKED", result["authority_state"])
        self.assertEqual("REFUSED_AUTHORITY_FORK", result["admission"])
        replay = evaluate_admission(value, evidence, self.root, forked, now=NOW, historical_digest=package_digest(value))
        self.assertEqual("HISTORICAL_ACCEPTANCE_REPLAY", replay["admission"])

    def test_fresh_custodians_and_total_replacement_need_no_sender_secret(self):
        change = transition(self.root, self.authority_private, "IN-P0", "IN-P1", self.terms1, "CM-replacement")
        package_before = self.pkg("before")
        proof_before = self.authorize(package_before)
        evidence = [change]

        for name in ("porter-a", "porter-b", "porter-c"):
            self.assertEqual("PACKAGE_SIGNATURE_VALID", verify_package(package_before, proof_before, self.root, self.current0())["proof_state"])

        package_after = self.pkg("after")
        proof_after = self.authorize(package_after, private=self.k1_private, introduction="IN-P1", key=self.k1, generation=1)
        for name in ("porter-d", "porter-e", "porter-f"):
            store = AuthorityStore(self.base / name, self.root)
            for item in evidence:
                store.retain(item)
            result = evaluate_admission(package_after, proof_after, self.root, store.knowledge(), now=NOW)
            self.assertEqual("AUTHORIZED_FOR_LOCAL_AC", result["admission"], name)

        self.assertEqual(proof_after, copy.deepcopy(proof_after))
        self.assertNotIn("porter-", repr(proof_after))

    def test_sender_key_compromise_is_relationship_scoped_but_authorizes_within_terms(self):
        attacker_package = self.pkg("sender-key-stolen")
        attacker_proof = self.authorize(attacker_package)
        self.assertEqual("AUTHORIZED_FOR_LOCAL_AC", evaluate_admission(attacker_package, attacker_proof, self.root, self.current0(), now=NOW)["admission"])

        another_recipient = self.pkg("transplant", to="another-host")
        transplanted = sign_package(
            self.k0_private,
            another_recipient,
            root=self.root["root"],
            introduction="IN-P0",
            authorization_key=authorization_key_id(self.k0_public, 0, "find-me", "another-host"),
            authorization_generation=0,
        )
        with self.assertRaises(AuthorizationRefused):
            verify_package(another_recipient, transplanted, self.root, self.current0())

        forbidden = self.pkg("widen", kind="admin.request")
        forbidden_proof = self.authorize(forbidden)
        self.assertEqual("REFUSED_KIND", evaluate_admission(forbidden, forbidden_proof, self.root, self.current0(), now=NOW)["admission"])

    def test_disjoint_depositor_topology_does_not_enter_authorization(self):
        alice_package = self.pkg("alice")
        alice_proof = self.authorize(alice_package)

        bob_private, bob_public = generate_keypair()
        bob_terms = self.terms(bob_public, 0)
        _, bob_authority_public = generate_keypair()
        bob_root = authority_root(
            "signing-host-bob-authority",
            bob_authority_public,
            "signing-host",
            "bob",
            "IN-BOB-0",
            bob_terms,
        )
        bob_package = package("bob", "signing-host", "signing.request", {"marker": "bob"}, ttl=3600)
        bob_key = authorization_key_id(bob_public, 0, "bob", "signing-host")
        bob_proof = sign_package(
            bob_private,
            bob_package,
            root=bob_root["root"],
            introduction="IN-BOB-0",
            authorization_key=bob_key,
            authorization_generation=0,
        )

        for custodian in ("porter-a", "porter-b"):
            self.assertEqual("PACKAGE_SIGNATURE_VALID", verify_package(alice_package, alice_proof, self.root, derive(self.root, []))["proof_state"], custodian)
        for custodian in ("porter-c", "porter-d"):
            self.assertEqual("PACKAGE_SIGNATURE_VALID", verify_package(bob_package, bob_proof, bob_root, derive(bob_root, []))["proof_state"], custodian)
        self.assertNotIn("porter-", repr(alice_proof) + repr(bob_proof))


if __name__ == "__main__":
    unittest.main()
