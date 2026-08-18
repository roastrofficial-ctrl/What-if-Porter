from __future__ import annotations

import base64
import json
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

from porter.daemon import Porter
from porter.native import public_key
from porter.protocol import atomic_write, package
from porter.rendezvous import (
    RendezvousKnowledge,
    RendezvousRefused,
    RendezvousUnavailable,
    continuity_public_key,
    sign_transition,
)


def operational_keypair():
    key = X25519PrivateKey.generate()
    private = base64.b64encode(
        key.private_bytes(
            serialization.Encoding.Raw,
            serialization.PrivateFormat.Raw,
            serialization.NoEncryption(),
        )
    ).decode()
    return private, public_key(private)


def continuity_keypair():
    key = Ed25519PrivateKey.generate()
    private = base64.b64encode(
        key.private_bytes(
            serialization.Encoding.Raw,
            serialization.PrivateFormat.Raw,
            serialization.NoEncryption(),
        )
    ).decode()
    return private, continuity_public_key(private)


def free_port():
    stream = socket.socket()
    stream.bind(("127.0.0.1", 0))
    value = stream.getsockname()[1]
    stream.close()
    return value


class RendezvousKnowledgeExperiment(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.old_private, self.old_public = operational_keypair()
        self.new_private, self.new_public = operational_keypair()
        self.authority_private, self.authority_public = continuity_keypair()
        self.configured = {
            "harmonicdb": {
                "host": "carrier-a",
                "port": 7411,
                "public_key": self.old_public,
            }
        }
        self.knowledge = RendezvousKnowledge(
            self.root, self.configured, {"harmonicdb": self.authority_public}
        )

    def tearDown(self):
        self.tmp.cleanup()

    def transition(self, **changes):
        current = self.knowledge.status("harmonicdb")
        values = {
            "private_key": self.authority_private,
            "porter": "harmonicdb",
            "generation": current["generation"] + 1,
            "predecessor": current["rendezvous"],
            "location": {"host": "carrier-b", "port": 9177},
            "carriage_public_key": self.new_public,
        }
        values.update(changes)
        return sign_transition(**values)

    def test_location_and_operational_key_change_preserve_identity(self):
        before = self.knowledge.status("harmonicdb")
        claim = self.transition()
        after = self.knowledge.accept(claim)
        self.assertEqual("harmonicdb", after["porter"])
        self.assertEqual(1, after["generation"])
        self.assertEqual({"host": "carrier-b", "port": 9177}, after["location"])
        self.assertEqual(self.new_public, after["carriage_public_key"])
        self.assertNotEqual(before["rendezvous"], after["rendezvous"])

    def test_endpoint_or_operational_key_possession_cannot_claim_identity(self):
        attacker, _ = continuity_keypair()
        forged = sign_transition(
            attacker,
            "harmonicdb",
            1,
            self.knowledge.status("harmonicdb")["rendezvous"],
            {"host": "stolen-old-location", "port": 7411},
            self.old_public,
        )
        before = len(list(self.root.rglob("*.json")))
        with self.assertRaisesRegex(
            RendezvousRefused, "RENDEZVOUS_CONTINUITY_NOT_PROVEN"
        ):
            self.knowledge.accept(forged)
        self.assertEqual(before, len(list(self.root.rglob("*.json"))))

    def test_replay_cannot_move_current_knowledge_backwards(self):
        first = self.transition()
        self.knowledge.accept(first)
        second = sign_transition(
            self.authority_private,
            "harmonicdb",
            2,
            first["rendezvous"],
            {"host": "unexpected-name-c", "port": 9300},
            self.new_public,
        )
        self.knowledge.accept(second)
        self.knowledge.accept(first)
        self.assertEqual(2, self.knowledge.status("harmonicdb")["generation"])

    def test_out_of_order_is_not_stored_and_retry_later_advances(self):
        first = self.transition()
        second = sign_transition(
            self.authority_private,
            "harmonicdb",
            2,
            first["rendezvous"],
            {"host": "carrier-c", "port": 9300},
            self.new_public,
        )
        with self.assertRaisesRegex(
            RendezvousRefused, "RENDEZVOUS_PREDECESSOR_NOT_KNOWN"
        ):
            self.knowledge.accept(second)
        self.assertFalse(
            (self.root / "rendezvous" / "facts" / f"{second['rendezvous']}.json").exists()
        )
        self.knowledge.accept(first)
        self.knowledge.accept(second)
        self.assertEqual(2, self.knowledge.status("harmonicdb")["generation"])

    def test_authority_equivocation_suspends_rendezvous_choice(self):
        first = self.transition()
        conflict = self.transition(location={"host": "carrier-c", "port": 9999})
        self.knowledge.accept(first)
        status = self.knowledge.accept(conflict)
        self.assertEqual("CONTINUITY_CONFLICT_OBSERVED", status["knowledge"])
        with self.assertRaises(RendezvousUnavailable):
            self.knowledge.route("harmonicdb")

    def test_future_activation_expiry_and_restart_are_local_knowledge(self):
        now = int(time.time() * 1000)
        self.knowledge.now = lambda: now
        future = self.transition(activates_at_ms=now + 100, expires_at_ms=now + 200)
        self.knowledge.accept(future)
        self.assertEqual(0, self.knowledge.status("harmonicdb")["generation"])
        self.knowledge.now = lambda: now + 150
        self.assertEqual(1, self.knowledge.route("harmonicdb")["generation"])
        self.knowledge.now = lambda: now + 250
        with self.assertRaisesRegex(RendezvousUnavailable, "KNOWN_RENDEZVOUS_EXPIRED"):
            self.knowledge.route("harmonicdb")
        self.assertEqual("harmonicdb", self.knowledge.status("harmonicdb")["porter"])

    def test_future_announcement_cannot_be_silently_cancelled_or_replaced(self):
        now = int(time.time() * 1000)
        self.knowledge.now = lambda: now
        future = self.transition(activates_at_ms=now + 100, expires_at_ms=now + 200)
        replacement = self.transition(
            location={"host": "cancelled-in-favour-of-c", "port": 9300},
            activates_at_ms=now + 100,
            expires_at_ms=now + 200,
        )
        self.knowledge.accept(future)
        status = self.knowledge.accept(replacement)
        self.assertEqual("CONTINUITY_CONFLICT_OBSERVED", status["knowledge"])

    def test_crash_after_fact_reconstructs_one_current_answer(self):
        claim = self.transition()
        with self.assertRaisesRegex(RuntimeError, "after rendezvous fact"):
            self.knowledge.accept(claim, fail_after="fact")
        recovered = RendezvousKnowledge(
            self.root, self.configured, {"harmonicdb": self.authority_public}
        )
        self.assertEqual(claim["rendezvous"], recovered.status("harmonicdb")["rendezvous"])


class NativeContinuityExperiment(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.a_root, self.b_root = base / "a", base / "b"
        self.a_private, self.a_public = operational_keypair()
        self.b_old_private, self.b_old_public = operational_keypair()
        self.b_new_private, self.b_new_public = operational_keypair()
        self.b_authority_private, self.b_authority_public = continuity_keypair()
        self.a_port, self.b_old_port, self.b_new_port = free_port(), free_port(), free_port()
        self.a = Porter(
            "find-me",
            self.a_root,
            {},
            native_private_key=self.a_private,
            native_rendezvous={
                "harmonicdb": {
                    "host": "127.0.0.1",
                    "port": self.b_old_port,
                    "public_key": self.b_old_public,
                }
            },
            native_listen=f"127.0.0.1:{self.a_port}",
            continuity_authorities={"harmonicdb": self.b_authority_public},
        )
        self.b = self.make_b(self.b_old_private, self.b_old_port)
        for porter in (self.a, self.b):
            threading.Thread(target=porter.native.serve_forever, daemon=True).start()
        time.sleep(0.03)

    def make_b(self, private, listen_port):
        return Porter(
            "harmonicdb",
            self.b_root,
            {},
            native_private_key=private,
            native_rendezvous={
                "find-me": {
                    "host": "127.0.0.1",
                    "port": self.a_port,
                    "public_key": self.a_public,
                }
            },
            native_listen=f"127.0.0.1:{listen_port}",
        )

    def tearDown(self):
        for porter in (self.a, self.b):
            porter.native.stop()
        time.sleep(0.02)
        self.tmp.cleanup()

    def pump(self, predicate, limit=300):
        for _ in range(limit):
            self.a.native.tick()
            self.b.native.tick()
            if predicate():
                return
            time.sleep(0.01)
        self.fail("native continuity did not converge")

    def movement_claim(self):
        current = self.a.native.knowledge.status("harmonicdb")
        return sign_transition(
            self.b_authority_private,
            "harmonicdb",
            1,
            current["rendezvous"],
            {"host": "127.0.0.1", "port": self.b_new_port},
            self.b_new_public,
        )

    def move_b(self):
        self.b.native.stop()
        time.sleep(0.25)
        self.b = self.make_b(self.b_new_private, self.b_new_port)
        threading.Thread(target=self.b.native.serve_forever, daemon=True).start()
        time.sleep(0.03)

    def test_preannouncement_moves_lodged_package_without_new_identity(self):
        claim = self.movement_claim()
        self.a.native.knowledge.accept(claim)
        self.move_b()
        value = package("find-me", "harmonicdb", "demo.move", {"same": True})
        atomic_write(self.a_root / "outgoing", value)
        self.pump(lambda: (self.a_root / "receipts" / f"{value['package']}.json").exists())
        self.assertTrue((self.b_root / "acceptances" / f"{value['package']}.json").exists())

    def test_missed_movement_recovers_from_signed_evidence_after_old_endpoint_dies(self):
        claim = self.movement_claim()
        value = package("find-me", "harmonicdb", "demo.move", {"lodged_before": True})
        atomic_write(self.a_root / "outgoing", value)
        self.move_b()
        for _ in range(3):
            self.a.native.tick()
        unit = json.loads(
            (self.a_root / "native" / "outgoing" / f"CU-PKG-{value['package']}.json").read_text()
        )
        self.assertEqual("KNOWN_RENDEZVOUS_ATTEMPT_FAILED", unit["last_attempt"])
        self.b.native.queue_rendezvous("find-me", claim)
        self.pump(lambda: (self.a_root / "receipts" / f"{value['package']}.json").exists())
        self.assertEqual(value["package"], json.loads(
            (self.b_root / "acceptances" / f"{value['package']}.json").read_text()
        )["package"]["package"])
