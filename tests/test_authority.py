from __future__ import annotations

import copy
import itertools
import tempfile
import unittest
from pathlib import Path

from porter.authority import (
    AuthorityEvidenceRefused,
    AuthorityStore,
    authority_root,
    authorize_new,
    derive,
    generate_keypair,
    transition,
)


TERMS_0 = {"kinds": ["signing.request"], "expires_at": 2000000000, "limit": 10}
TERMS_1 = {"kinds": ["signing.request"], "expires_at": 2000000000, "limit": 8}
TERMS_2 = {"kinds": ["signing.request"], "expires_at": 2000000000, "limit": 6}
TERMS_3 = {"kinds": ["signing.request"], "expires_at": 2000000000, "limit": 4}


class PortableAuthorityExperiment(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.private, self.public = generate_keypair()
        self.root = authority_root(
            "signing-host-offline-authority",
            self.public,
            "signing-host",
            "find-me",
            "IN-P0",
            TERMS_0,
        )
        self.p01 = transition(self.root, self.private, "IN-P0", "IN-P1", TERMS_1, "CM-01")
        self.p12 = transition(self.root, self.private, "IN-P1", "IN-P2", TERMS_2, "CM-12")
        self.p23 = transition(self.root, self.private, "IN-P2", "IN-P3", TERMS_3, "CM-23")

    def tearDown(self):
        self.temporary.cleanup()

    def store(self, name: str) -> AuthorityStore:
        return AuthorityStore(self.base / name, self.root)

    def test_out_of_order_restart_and_replay_are_evidence_set_deterministic(self):
        orders = (
            (self.p23, self.p01, self.p12),
            (self.p12, self.p23, self.p01),
            (self.p01, self.p12, self.p23),
        )
        final = []
        for index, order in enumerate(orders):
            store = self.store(f"custodian-{index}")
            first = store.retain(order[0])
            if order[0] is not self.p01:
                self.assertEqual("PENDING", first["state"])
            store = AuthorityStore(store.path, self.root)
            store.retain(order[1])
            final.append(store.retain(order[2]))
            self.assertEqual(final[-1], store.retain(order[2]))
        self.assertEqual(1, len({repr(value) for value in final}))
        self.assertEqual("CURRENT", final[0]["state"])
        self.assertEqual("IN-P3", final[0]["current"])

        for order in itertools.permutations((self.p01, self.p12, self.p23)):
            result = derive(self.root, list(order))
            self.assertEqual(final[0], result)

    def test_hidden_fork_becomes_order_independent_portable_fork_evidence(self):
        fork_x = transition(self.root, self.private, "IN-P1", "IN-P2-X", TERMS_2, "CM-X")
        fork_y = transition(self.root, self.private, "IN-P1", "IN-P2-Y", TERMS_2, "CM-Y")
        d = self.store("d")
        d.retain(self.p01)
        before = d.retain(fork_x)
        self.assertEqual("CURRENT", before["state"])
        self.assertEqual("IN-P2-X", before["current"])
        self.assertNotIn("fork", before["state"].lower())

        d = AuthorityStore(d.path, self.root)
        after = d.retain(fork_y)
        self.assertEqual("FORKED", after["state"])
        self.assertEqual(["IN-P2-X", "IN-P2-Y"], sorted(branch["successor"] for branch in after["branches"]))

        e = self.store("unrelated-verifier")
        for value in reversed(d.export()):
            e.retain(value)
        self.assertEqual(after, e.knowledge())
        self.assertEqual(after, derive(self.root, [self.p01, fork_y, fork_x, fork_x]))

    def test_known_fork_refuses_new_ac_without_rewriting_historical_acceptance(self):
        fork_x = transition(self.root, self.private, "IN-P1", "IN-X", TERMS_2, "CM-X")
        fork_y = transition(self.root, self.private, "IN-P1", "IN-Y", TERMS_2, "CM-Y")
        store = self.store("admission")
        store.retain(self.p01)
        x_only = store.retain(fork_x)
        self.assertEqual("NEW_ACCEPTANCE_AUTHORIZED", authorize_new(x_only, "IN-X"))
        historical = {"PKG-before-fork": "AC-under-X"}

        forked = store.retain(fork_y)
        for introduction in ("IN-X", "IN-Y", "IN-P1"):
            with self.assertRaisesRegex(AuthorityEvidenceRefused, "fork"):
                authorize_new(forked, introduction)
        self.assertEqual(
            "HISTORICAL_ACCEPTANCE_REPLAY",
            authorize_new(forked, "IN-X", historical_replay=True),
        )
        self.assertEqual({"PKG-before-fork": "AC-under-X"}, historical)

    def test_signature_binds_scope_continuity_terms_generation_and_ceremony(self):
        mutations = {
            "recipient": "another-host",
            "sender": "another-sender",
            "predecessor": "IN-other",
            "successor": "IN-other",
            "successor_terms": {"kinds": ["admin"], "expires_at": 9999999999},
            "ceremony": "CM-substituted",
            "authority": "unknown-authority",
            "authority_generation": 99,
            "root": "AR-another",
        }
        for field, replacement in mutations.items():
            with self.subTest(field=field):
                attacked = copy.deepcopy(self.p01)
                attacked[field] = replacement
                with self.assertRaises(AuthorityEvidenceRefused):
                    derive(self.root, [attacked])

        unknown_private, _ = generate_keypair()
        falsely_signed = transition(self.root, unknown_private, "IN-P0", "IN-evil", TERMS_1, "CM-evil")
        with self.assertRaisesRegex(AuthorityEvidenceRefused, "signature"):
            derive(self.root, [falsely_signed])

        retired_root = authority_root(
            self.root["authority"],
            self.public,
            self.root["recipient"],
            self.root["sender"],
            self.root["genesis"],
            self.root["genesis_terms"],
            generation=1,
        )
        with self.assertRaises(AuthorityEvidenceRefused):
            derive(retired_root, [self.p01])

    def test_corruption_and_duplicate_delivery_change_no_authority_knowledge(self):
        store = self.store("corruption")
        expected = store.retain(self.p01)
        self.assertEqual(expected, store.retain(self.p01))
        path = next(store.evidence.glob("AT-*.json"))
        path.write_text("{truncated")
        with self.assertRaisesRegex(AuthorityEvidenceRefused, "corrupt"):
            AuthorityStore(store.path, self.root).knowledge()

    def test_honest_and_forked_results_survive_total_infrastructure_replacement(self):
        old_honest = self.store("old-honest")
        for value in (self.p01, self.p12):
            old_honest.retain(value)
        honest_evidence = old_honest.export()
        honest_before = old_honest.knowledge()

        fork_x = transition(self.root, self.private, "IN-P1", "IN-X", TERMS_2, "CM-X")
        fork_y = transition(self.root, self.private, "IN-P1", "IN-Y", TERMS_2, "CM-Y")
        old_forked = self.store("old-forked")
        for value in (self.p01, fork_x, fork_y):
            old_forked.retain(value)
        fork_evidence = old_forked.export()
        fork_before = old_forked.knowledge()

        for path in (old_honest.path, old_forked.path):
            for item in sorted(path.rglob("*"), key=lambda value: len(value.parts), reverse=True):
                if item.is_file():
                    item.unlink()
                elif item.is_dir():
                    item.rmdir()

        new_honest = self.store("new-honest")
        new_forked = self.store("new-forked")
        for value in reversed(honest_evidence):
            new_honest.retain(value)
        for value in reversed(fork_evidence):
            new_forked.retain(value)
        self.assertEqual(honest_before, new_honest.knowledge())
        self.assertEqual(fork_before, new_forked.knowledge())

    def test_missing_root_is_unknown_not_evidence_of_no_fork(self):
        self.assertEqual("UNKNOWN", derive(None, [])["state"])


if __name__ == "__main__":
    unittest.main()
