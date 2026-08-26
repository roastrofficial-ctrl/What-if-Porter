from __future__ import annotations

import json
import shutil
import tempfile
import time
import unittest
from pathlib import Path

from porter.ceremony import CeremonyRefused, ceremony_proof, digest
from porter.daemon import Porter
from porter.introduction import AdmissionRefused, proof, relationship_id
from porter.protocol import package


OLD = "plural-standing-predecessor"
NEW = "plural-standing-successor"
THIRD = "plural-standing-third"
FORK_X = "plural-standing-fork-x"
FORK_Y = "plural-standing-fork-y"
CEREMONY = "plural-standing-ceremonial-root"
EXPIRY = int(time.time()) + 86400


def terms(secret: str) -> dict:
    return {
        "secret": secret,
        "authority": "recipient-authority:offline",
        "kinds": ["signing.request"],
        "max_package_bytes": 16384,
        "max_outstanding_packages": 100,
        "max_outstanding_bytes": 1048576,
        "expires_at": EXPIRY,
    }


def config() -> dict:
    value = terms(OLD)
    value.update(
        {
            "ceremony_secret": CEREMONY,
            "ceremony_expires_at": EXPIRY,
            "ceremony_max_changes": 8,
            "ceremony_max_pending": 8,
            "ceremony_terms": {
                key: value[key]
                for key in (
                    "kinds",
                    "max_package_bytes",
                    "max_outstanding_packages",
                    "max_outstanding_bytes",
                    "expires_at",
                )
            },
        }
    )
    return value


class PluralStandingExperiment(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.origin = Porter(
            "find-me",
            self.base / "origin",
            {},
            relationships={"signing-host": config()},
            require_introductions=True,
        )
        self.custodians = {
            name: self.new_custodian(name) for name in ("porter-a", "porter-b", "porter-c")
        }
        self.predecessor = relationship_id("signing-host", "find-me")

    def tearDown(self):
        self.temporary.cleanup()

    def new_custodian(self, name: str) -> Porter:
        # Each root is independent. The name is deliberately absent from
        # correspondence identity and Standing facts.
        return Porter(
            "signing-host",
            self.base / name,
            {},
            relationships={"find-me": config()},
            require_introductions=True,
        )

    def draft(self, predecessor: str, secret: str, ceremony_id: str) -> dict:
        return self.origin.ceremonies.draft(
            "signing-host",
            predecessor,
            secret,
            terms(secret),
            "COMPROMISE_KNOWN",
            ceremony_id=ceremony_id,
        )

    def present(self, custodian: Porter, value: dict) -> dict:
        return custodian.ceremonies.receive(value, ceremony_proof(CEREMONY, value))

    def correspondence(self, marker: str) -> dict:
        return package(
            "find-me",
            "signing-host",
            "signing.request",
            {"marker": marker},
            ttl=3600,
        )

    def decision(self, custodian: Porter, marker: str, secret: str) -> str:
        value = self.correspondence(marker)
        try:
            custodian.deposit(value, admission=proof(secret, value))
            return "AC"
        except AdmissionRefused:
            return "REFUSED"

    def test_deliberate_divergence_is_locally_coherent_and_eventually_converges(self):
        ceremony = self.draft(self.predecessor, NEW, "CM-plural-successor")
        a, b, c = (self.custodians[name] for name in ("porter-a", "porter-b", "porter-c"))

        self.assertEqual("APPLIED", self.present(a, ceremony)["state"])
        self.assertEqual(
            [("REFUSED", "AC"), ("AC", "REFUSED"), ("AC", "REFUSED")],
            [
                (self.decision(custodian, f"t1-old-{index}", OLD), self.decision(custodian, f"t1-new-{index}", NEW))
                for index, custodian in enumerate((a, b, c))
            ],
        )

        self.assertEqual("APPLIED", self.present(b, ceremony)["state"])
        self.assertEqual(
            [("REFUSED", "AC"), ("REFUSED", "AC"), ("AC", "REFUSED")],
            [
                (self.decision(custodian, f"t2-old-{index}", OLD), self.decision(custodian, f"t2-new-{index}", NEW))
                for index, custodian in enumerate((a, b, c))
            ],
        )

        self.assertEqual("APPLIED", self.present(c, ceremony)["state"])
        for index, custodian in enumerate((a, b, c)):
            self.assertEqual("REFUSED", self.decision(custodian, f"t3-old-{index}", OLD))
            self.assertEqual("AC", self.decision(custodian, f"t3-new-{index}", NEW))

        changes = [
            json.loads(next((custodian.ipc / "introductions/changes").glob("IN-*.json")).read_text())
            for custodian in (a, b, c)
        ]
        self.assertEqual({ceremony["ceremony"]}, {change["cause"] for change in changes})
        self.assertEqual({ceremony["successor"]}, {change["successor"] for change in changes})
        self.assertEqual(3, len({change["change"] for change in changes}))

    def test_delayed_and_new_custodians_replay_authorized_history_without_siblings(self):
        first = self.draft(self.predecessor, NEW, "CM-history-one")
        second = self.draft(first["successor"], THIRD, "CM-history-two")
        a = self.custodians["porter-a"]
        self.present(a, first)
        self.present(a, second)

        delayed = self.custodians["porter-c"]
        self.assertEqual("PENDING_PREDECESSOR", self.present(delayed, second)["state"])
        self.assertEqual("APPLIED", self.present(delayed, first)["state"])
        self.assertEqual(second["successor"], delayed.admission.active["find-me"]["introduction"])

        newcomer = self.new_custodian("porter-d")
        self.assertEqual("PENDING_PREDECESSOR", self.present(newcomer, second)["state"])
        self.present(newcomer, first)
        self.assertEqual("REFUSED", self.decision(newcomer, "newcomer-old", OLD))
        self.assertEqual("REFUSED", self.decision(newcomer, "newcomer-middle", NEW))
        self.assertEqual("AC", self.decision(newcomer, "newcomer-current", THIRD))

        # D learned from original ceremony values and proofs. No A history or
        # result was copied, and A is not mentioned anywhere in D's facts.
        encoded = json.dumps(
            [json.loads(path.read_text()) for path in (newcomer.ipc / "introductions/changes").glob("IN-*.json")]
        )
        self.assertNotIn("porter-a", encoded)

    def test_authorized_fork_is_locally_valid_and_replay_order_has_no_canonical_answer(self):
        fork_x = self.draft(self.predecessor, FORK_X, "CM-fork-x")
        fork_y = self.draft(self.predecessor, FORK_Y, "CM-fork-y")
        a, b = self.custodians["porter-a"], self.custodians["porter-b"]

        self.assertEqual("APPLIED", self.present(a, fork_x)["state"])
        self.assertEqual("APPLIED", self.present(b, fork_y)["state"])
        self.assertEqual("AC", self.decision(a, "a-x", FORK_X))
        self.assertEqual("REFUSED", self.decision(a, "a-y", FORK_Y))
        self.assertEqual("AC", self.decision(b, "b-y", FORK_Y))
        self.assertEqual("REFUSED", self.decision(b, "b-x", FORK_X))

        with self.assertRaises(CeremonyRefused):
            self.present(a, fork_y)
        with self.assertRaises(CeremonyRefused):
            self.present(b, fork_x)

        d = self.new_custodian("porter-d")
        e = self.new_custodian("porter-e")
        self.present(d, fork_x)
        self.present(e, fork_y)
        with self.assertRaises(CeremonyRefused):
            self.present(d, fork_y)
        with self.assertRaises(CeremonyRefused):
            self.present(e, fork_x)
        self.assertEqual(fork_x["successor"], d.admission.active["find-me"]["introduction"])
        self.assertEqual(fork_y["successor"], e.admission.active["find-me"]["introduction"])

        # An observer possessing both original authorized values can detect the
        # fork, but neither branch proves which successor is globally current.
        self.assertEqual(fork_x["predecessor"], fork_y["predecessor"])
        self.assertNotEqual(fork_x["successor"], fork_y["successor"])
        self.assertNotEqual(digest(fork_x), digest(fork_y))
        self.assertNotEqual(
            ceremony_proof(CEREMONY, fork_x), ceremony_proof(CEREMONY, fork_y)
        )

    def test_nonforking_authority_survives_total_custodian_replacement(self):
        ceremony = self.draft(self.predecessor, NEW, "CM-total-replacement")
        originals = list(self.custodians.values())
        for custodian in originals:
            self.present(custodian, ceremony)

        replacements = [self.new_custodian(name) for name in ("porter-d", "porter-e", "porter-f")]
        for custodian in replacements:
            self.present(custodian, ceremony)
            self.assertEqual("REFUSED", self.decision(custodian, f"old-{custodian.ipc.name}", OLD))
            self.assertEqual("AC", self.decision(custodian, f"new-{custodian.ipc.name}", NEW))

        for custodian in originals:
            shutil.rmtree(custodian.ipc)
        self.assertTrue(all(not custodian.ipc.exists() for custodian in originals))
        self.assertEqual(
            {ceremony["successor"]},
            {custodian.admission.active["find-me"]["introduction"] for custodian in replacements},
        )
        self.assertEqual(
            {"signing-host"},
            {custodian.identity for custodian in replacements},
        )


if __name__ == "__main__":
    unittest.main()
