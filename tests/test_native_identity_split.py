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

from porter.custody import collect_package
from porter.daemon import Porter
from porter.host_runtime import HostRuntime
from porter.introduction import relationship_id
from porter.native import public_key, seal
from porter.protocol import atomic_write, package
from porter.rendezvous import continuity_public_key, sign_transition


OLD = "split-standing-old"; NEW = "split-standing-new"; CEREMONY = "split-ceremony"


def carriage_keypair():
    key = X25519PrivateKey.generate(); private = base64.b64encode(key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())).decode()
    return private, public_key(private)


def continuity_keypair():
    key = Ed25519PrivateKey.generate(); private = base64.b64encode(key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())).decode()
    return private, continuity_public_key(private)


def free_port():
    stream = socket.socket(); stream.bind(("127.0.0.1", 0)); value = stream.getsockname()[1]; stream.close(); return value


def terms(kind, secret=OLD, expiry=None):
    expiry = expiry or int(time.time()) + 86400
    return {"secret": secret, "authority": "split-lab", "kinds": [kind], "max_package_bytes": 8192, "max_outstanding_packages": 50, "max_outstanding_bytes": 65536, "expires_at": expiry, "ceremony_secret": CEREMONY, "ceremony_expires_at": expiry, "ceremony_max_changes": 8, "ceremony_max_pending": 4, "ceremony_terms": {"kinds": [kind], "max_package_bytes": 8192, "max_outstanding_packages": 50, "max_outstanding_bytes": 65536, "expires_at": expiry}}


class RecordingAdapter:
    def __init__(self): self.collections = []
    def dispatch(self, dispatch_id, collection):
        self.collections.append(collection); return {"contract": "PORTER-HOST-ADAPTER/1", "dispatch": dispatch_id, "runtime_observation": "ADAPTER_RETURNED_CONTROL"}
    def close(self): pass


class ProductionNativeIdentitySplitExperiment(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(); self.base = Path(self.temporary.name)
        self.expiry = int(time.time()) + 86400
        self.a_root, self.b_root = self.base / "a", self.base / "b"
        self.a_key, self.a_public = carriage_keypair(); self.b_key, self.b_public = carriage_keypair(); self.c_key, self.c_public = carriage_keypair()
        self.a_port, self.b_port = free_port(), free_port(); self.b_authority_private, self.b_authority_public = continuity_keypair()
        self.a = self.make_a(); self.b = self.make_b(self.b_key, self.b_port)
        for porter in (self.a, self.b): threading.Thread(target=porter.native.serve_forever, daemon=True).start()
        time.sleep(.03)

    def make_a(self):
        return Porter("find-me", self.a_root, {}, relationships={"harmonicdb": terms("porter.return", expiry=self.expiry)}, require_introductions=True, native_private_key=self.a_key, native_custodian_identity="porter-a", native_recipient_custodians={"harmonicdb": "porter-b"}, native_rendezvous={"porter-b": {"host": "127.0.0.1", "port": self.b_port, "public_key": self.b_public}, "porter-c": {"host": "127.0.0.1", "port": free_port(), "public_key": self.c_public}}, native_listen=f"127.0.0.1:{self.a_port}", continuity_authorities={"porter-b": self.b_authority_public})

    def make_b(self, private, listen_port):
        return Porter("harmonicdb", self.b_root, {}, relationships={"find-me": terms("hdbe.call", expiry=self.expiry)}, require_introductions=True, native_private_key=private, native_custodian_identity="porter-b", native_recipient_custodians={"find-me": "porter-a"}, native_rendezvous={"porter-a": {"host": "127.0.0.1", "port": self.a_port, "public_key": self.a_public}}, native_listen=f"127.0.0.1:{listen_port}")

    def tearDown(self):
        for porter in (self.a, self.b):
            if porter.native: porter.native.stop()
        time.sleep(.02); self.temporary.cleanup()

    def pump(self, predicate, limit=350):
        for _ in range(limit):
            self.a.native.tick(); self.b.native.tick()
            if predicate(): return
            time.sleep(.01)
        self.fail("split native carriage did not converge")

    def lodge(self, value):
        atomic_write(self.a_root / "outgoing", value)
        self.pump(lambda: (self.a_root / "receipts" / f"{value['package']}.json").exists())

    def test_package_ac_and_attribution_cross_split_identities(self):
        value = package("find-me", "harmonicdb", "hdbe.call", {"split": True}, ttl=3600); self.lodge(value)
        accepted = json.loads((self.b_root / "acceptances" / f"{value['package']}.json").read_text())
        self.assertEqual("harmonicdb", accepted["recipient"]); self.assertEqual("harmonicdb", accepted["package"]["to"])
        receipt = json.loads((self.a_root / "receipts" / f"{value['package']}.json").read_text()); self.assertEqual("harmonicdb", receipt["recipient"])
        attributions = [json.loads(path.read_text()) for path in (self.a_root / "native/attribution").glob("CU-EV-*.json")]
        self.assertTrue(any(item["custodian"] == "porter-a" and item["peer_custodian"] == "porter-b" for item in attributions))
        self.assertNotIn("porter-b", json.dumps(value))

    def test_refusal_and_wrong_custodian_response_do_not_cross_ac(self):
        refused = package("find-me", "harmonicdb", "forbidden.kind", {}, ttl=3600); atomic_write(self.a_root / "outgoing", refused)
        self.pump(lambda: (self.a_root / "refused" / f"{refused['package']}.json").exists())
        self.assertFalse((self.b_root / "acceptances" / f"{refused['package']}.json").exists())
        outstanding = package("find-me", "harmonicdb", "hdbe.call", {"wrong": "custodian"}, ttl=3600); atomic_write(self.a_root / "outgoing", outstanding); self.a.native.stage_host_outgoing()
        fake = {"protocol": "PORTER/1", "kind": "RECEIPT", "package": outstanding["package"], "state": "REMOTE_PORTER_DURABLY_ACCEPTED", "recipient": "harmonicdb", "acceptance": "AC-fake", "accepted_at_ms": 1, "package_digest": "sha256:fake", "attests": "RECIPIENT_PORTER_ACCEPTED_RESPONSIBILITY"}
        frame = seal(fake, "porter-c", self.c_key, "porter-a", self.a_public, "ACCEPTANCE_EVIDENCE", f"CU-EV-{outstanding['package']}")
        from porter.native import open_frame
        envelope, clear = open_frame(frame[9:], "porter-a", self.a_key, {"porter-c": self.c_public})
        with self.assertRaisesRegex(Exception, "another custodian"): self.a.native.receive(envelope, clear)
        self.assertFalse((self.a_root / "receipts" / f"{outstanding['package']}.json").exists())

    def test_host_runtime_and_return_preserve_served_recipient(self):
        value = package("find-me", "harmonicdb", "hdbe.call", {"runtime": True}, ttl=3600); self.lodge(value)
        adapter = RecordingAdapter(); runtime = HostRuntime(ipc=self.b_root, host="harmonicdb", adapter=adapter, kinds={"hdbe.call"}, batch_size=10, idle_ms=10, journal=self.b_root / "runtime.jsonl")
        self.assertEqual(1, runtime.visit()); self.assertEqual(value["package"], adapter.collections[0]["package"]["package"])
        returned = package("harmonicdb", "find-me", "porter.return", {"ok": True}, in_reply_to=value["package"], ttl=3600); atomic_write(self.b_root / "outgoing", returned)
        self.pump(lambda: (self.b_root / "receipts" / f"{returned['package']}.json").exists())
        fact = collect_package(self.a_root, returned["package"], "find-me-host")
        self.assertEqual("find-me", fact["package"]["to"]); self.assertEqual(value["package"], fact["package"]["in_reply_to"])

    def test_ceremony_targets_served_recipient_through_custodian(self):
        predecessor = relationship_id("harmonicdb", "find-me")
        successor_terms = terms("hdbe.call", NEW, self.expiry); successor_terms = {key: successor_terms[key] for key in ("kinds", "max_package_bytes", "max_outstanding_packages", "max_outstanding_bytes", "expires_at")}
        value = self.a.ceremonies.draft("harmonicdb", predecessor, NEW, successor_terms, "SPLIT_IDENTITY_RENEWAL")
        self.a.ceremonies.lodge(value)
        self.pump(lambda: (self.a_root / "ceremonies/receipts" / f"{value['ceremony']}.json").exists())
        self.assertEqual(value["successor"], self.b.admission.active["find-me"]["introduction"])
        attrs = [json.loads(path.read_text()) for path in (self.a_root / "native/attribution").glob("CU-CR-*.json")]
        self.assertTrue(any(item["peer_custodian"] == "porter-b" for item in attrs))

    def test_missed_custodian_movement_recovers_without_host_or_package_rename(self):
        current = self.a.native.knowledge.status("porter-b"); new_private, new_public = carriage_keypair(); new_port = free_port()
        transition = sign_transition(self.b_authority_private, "porter-b", 1, current["rendezvous"], {"host": "127.0.0.1", "port": new_port}, new_public)
        value = package("find-me", "harmonicdb", "hdbe.call", {"moved": True}, ttl=3600); atomic_write(self.a_root / "outgoing", value)
        self.b.native.stop(); time.sleep(.25)
        self.b = self.make_b(new_private, new_port); threading.Thread(target=self.b.native.serve_forever, daemon=True).start(); time.sleep(.03)
        for _ in range(3): self.a.native.tick()
        queued = json.loads((self.a_root / "native/outgoing" / f"CU-PKG-{value['package']}.json").read_text())
        self.assertEqual("KNOWN_RENDEZVOUS_ATTEMPT_FAILED", queued["last_attempt"])
        self.b.native.queue_rendezvous("porter-a", transition)
        self.pump(lambda: (self.a_root / "receipts" / f"{value['package']}.json").exists())
        self.assertTrue((self.b_root / "acceptances" / f"{value['package']}.json").exists())
        self.assertEqual("harmonicdb", value["to"]); self.assertEqual("porter-b", self.a.native.knowledge.status("porter-b")["porter"])

    def test_restart_preserves_old_evidence_and_split_configuration(self):
        value = package("find-me", "harmonicdb", "hdbe.call", {"restart": True}, ttl=3600); self.lodge(value)
        receipt_before = (self.a_root / "receipts" / f"{value['package']}.json").read_bytes()
        attribution_before = {path.name: path.read_bytes() for path in (self.a_root / "native/attribution").glob("*.json")}
        self.a.native.stop(); time.sleep(.25); self.a = self.make_a()
        self.assertEqual("porter-a", self.a.native.identity); self.assertEqual("find-me", self.a.native.served_recipient_identity)
        self.assertEqual(receipt_before, (self.a_root / "receipts" / f"{value['package']}.json").read_bytes())
        self.assertEqual(attribution_before, {path.name: path.read_bytes() for path in (self.a_root / "native/attribution").glob("*.json")})


if __name__ == "__main__": unittest.main()
