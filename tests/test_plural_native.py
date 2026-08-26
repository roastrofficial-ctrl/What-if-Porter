from __future__ import annotations

import base64
import json
import tempfile
import time
import unittest
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

from porter.daemon import Porter
from porter.evidence_identity import EvidenceKeyHistory, key_fact, verify_acceptance
from porter.introduction import AdmissionRefused, proof
from porter.native import NativeFrameRefused, public_key as carriage_public_key, seal
from porter.plural_native import NativeCustodian, PluralNativeSender, host_attention_round, unit_id
from porter.protocol import package
from porter.threshold import generate_private_key, public_key


def carriage_keypair():
    key = X25519PrivateKey.generate()
    private = base64.b64encode(key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())).decode()
    return private, carriage_public_key(private)


class PluralNativeCarriageExperiment(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(); self.base = Path(self.temporary.name)
        self.depositor_keys = {name: carriage_keypair() for name in ("alice", "bob")}
        self.custodians = {}; self.routes = {}; self.histories = {}
        for name in tuple("abcdefgh"):
            self.add_custodian(name)
        self.alice_root, self.bob_root = self.base / "alice", self.base / "bob"
        self.alice = self.sender("alice", self.alice_root, ("a", "b"))
        self.bob = self.sender("bob", self.bob_root, ("c", "d"))

    def tearDown(self): self.temporary.cleanup()

    def add_custodian(self, short):
        name = f"porter-{short}"; carriage_private, carriage_public = carriage_keypair(); continuity, evidence = generate_private_key(), generate_private_key()
        key = key_fact(continuity, name, 0, None, public_key(evidence), activates_at_ms=0, expires_at_ms=2**62)
        history = EvidenceKeyHistory(name, public_key(continuity), [key])
        terms = lambda depositor: {"secret": f"{depositor}:{name}", "authority": "plural-lab", "kinds": ["hdbe.call"], "max_package_bytes": 8192, "max_outstanding_packages": 50, "max_outstanding_bytes": 65536, "expires_at": int(time.time()) + 86400}
        porter = Porter("harmonicdb", self.base / name, {}, relationships={depositor: terms(depositor) for depositor in ("alice", "bob")}, require_introductions=True)
        endpoint = NativeCustodian(name, porter, carriage_private, {depositor: keys[1] for depositor, keys in self.depositor_keys.items()}, key, evidence)
        self.custodians[name] = endpoint; self.routes[name] = {"carriage_public_key": carriage_public}; self.histories[name] = history

    def sender(self, name, root, shorts):
        names = [f"porter-{short}" for short in shorts]
        routes = {custodian: {**self.routes[custodian], "admission_secret": f"{name}:{custodian}"} for custodian in names}
        return PluralNativeSender(name, root, self.depositor_keys[name][0], {"harmonicdb": routes}, {custodian: self.histories[custodian] for custodian in names})

    def deliver(self, sender, value, short):
        name = f"porter-{short}"; path = next(path for path in sender.queue(value, [name]) if name not in path.name or path.exists())
        # CU filename hashes the custodian, so select by its deterministic identity.
        path = sender.root / "plural-native/outgoing" / f"{unit_id(value['package'], name)}.json"
        return sender.deliver(path, self.custodians[name])

    def test_one_package_recipient_three_authenticated_cu_destinations(self):
        value = package("alice", "harmonicdb", "hdbe.call", {"plural": True}, ttl=3600)
        before = json.dumps(value, sort_keys=True)
        self.alice.destinations["harmonicdb"]["porter-e"] = {**self.routes["porter-e"], "admission_secret": "alice:porter-e"}
        self.alice.evidence_histories["porter-e"] = self.histories["porter-e"]
        evidence = [self.deliver(self.alice, value, short) for short in ("a", "b", "e")]
        self.assertEqual({"harmonicdb"}, {item["recipient"] for item in evidence})
        self.assertEqual({"porter-a", "porter-b", "porter-e"}, {item["custodian"] for item in evidence})
        self.assertEqual(before, json.dumps(value, sort_keys=True))
        self.assertEqual(3, len({item["receipt"]["acceptance"] for item in evidence}))

    def test_alice_and_bob_disjoint_knowledge_one_host_attention_round(self):
        alice = package("alice", "harmonicdb", "hdbe.call", {"from": "alice"}, ttl=3600)
        bob = package("bob", "harmonicdb", "hdbe.call", {"from": "bob"}, ttl=3600)
        self.deliver(self.alice, alice, "b"); self.deliver(self.bob, bob, "d")
        self.assertEqual({"porter-a", "porter-b"}, self.alice.known_custodians("harmonicdb"))
        self.assertEqual({"porter-c", "porter-d"}, self.bob.known_custodians("harmonicdb"))
        self.assertFalse(self.alice.known_custodians("harmonicdb") & self.bob.known_custodians("harmonicdb"))
        round_fact = host_attention_round(self.base / "host", [("porter-b", self.base / "porter-b", alice["package"]), ("porter-d", self.base / "porter-d", bob["package"])], "harmonicdb-host")
        self.assertEqual({alice["package"], bob["package"]}, {item["package"] for item in round_fact["observations"]})
        self.assertEqual({"COLLECTED"}, {item["state"] for item in round_fact["observations"]})

    def test_removed_custodian_leaves_outstanding_unit_then_unused_one_accepts(self):
        value = package("alice", "harmonicdb", "hdbe.call", {"outstanding": True}, ttl=3600)
        paths = self.alice.queue(value, ["porter-a", "porter-b"])
        b_path = self.alice.root / "plural-native/outgoing" / f"{unit_id(value['package'], 'porter-b')}.json"
        self.alice.deliver(b_path, self.custodians["porter-b"])
        a_path = self.alice.root / "plural-native/outgoing" / f"{unit_id(value['package'], 'porter-a')}.json"
        self.assertTrue(a_path.exists())
        del self.alice.destinations["harmonicdb"]["porter-a"]
        restarted = PluralNativeSender("alice", self.alice_root, self.depositor_keys["alice"][0], self.alice.destinations, self.alice.evidence_histories)
        self.assertTrue(a_path.exists())
        restarted.destinations["harmonicdb"]["porter-e"] = {**self.routes["porter-e"], "admission_secret": "alice:porter-e"}
        restarted.evidence_histories["porter-e"] = self.histories["porter-e"]
        self.deliver(restarted, value, "e")
        self.assertTrue((self.base / "porter-e/acceptances" / f"{value['package']}.json").exists())

    def test_every_original_custodian_is_replaced_across_old_and_new_correspondence(self):
        old_alice = package("alice", "harmonicdb", "hdbe.call", {"era": "old-a"}, ttl=3600)
        old_bob = package("bob", "harmonicdb", "hdbe.call", {"era": "old-b"}, ttl=3600)
        self.deliver(self.alice, old_alice, "b"); self.deliver(self.bob, old_bob, "d")
        alice_new = self.sender("alice", self.alice_root, ("e", "f")); bob_new = self.sender("bob", self.bob_root, ("g", "h"))
        self.deliver(alice_new, old_alice, "e"); self.deliver(bob_new, old_bob, "g")
        new_alice = package("alice", "harmonicdb", "hdbe.call", {"era": "new-a"}, ttl=3600)
        new_bob = package("bob", "harmonicdb", "hdbe.call", {"era": "new-b"}, ttl=3600)
        self.deliver(alice_new, new_alice, "f"); self.deliver(bob_new, new_bob, "h")
        # Remove every original A-D store and endpoint.
        for short in "abcd":
            name = f"porter-{short}"
            for path in sorted((self.base / name).rglob("*"), key=lambda item: len(item.parts), reverse=True):
                if path.is_file(): path.unlink()
                elif path.is_dir(): path.rmdir()
            self.custodians.pop(name)
        round_fact = host_attention_round(self.base / "host", [("porter-e", self.base / "porter-e", old_alice["package"]), ("porter-g", self.base / "porter-g", old_bob["package"]), ("porter-f", self.base / "porter-f", new_alice["package"]), ("porter-h", self.base / "porter-h", new_bob["package"])], "harmonicdb-host")
        self.assertEqual(4, len(round_fact["observations"]))
        self.assertEqual({"COLLECTED"}, {item["state"] for item in round_fact["observations"]})

    def test_restart_preserves_actual_custodian_attribution(self):
        value = package("alice", "harmonicdb", "hdbe.call", {"restart": True}, ttl=3600)
        retained = self.deliver(self.alice, value, "b")
        restarted_porter = Porter("harmonicdb", self.base / "porter-b", {})
        self.custodians["porter-b"].porter = restarted_porter
        restarted_sender = self.sender("alice", self.alice_root, ("a", "b"))
        stored = json.loads((self.alice_root / "plural-native/evidence" / f"{value['package']}--porter-b.json").read_text())
        verify_acceptance(stored["statement"], restarted_sender.evidence_histories["porter-b"], expected_recipient="harmonicdb", expected_package=value["package"], expected_digest=stored["package_digest"])
        self.assertEqual("porter-b", stored["custodian"])
        self.assertEqual(retained["statement"], stored["statement"])

    def test_custodian_identity_cannot_be_forced_into_package_or_wrong_endpoint(self):
        value = package("alice", "harmonicdb", "hdbe.call", {"identity": "pressure"}, ttl=3600)
        self.assertNotIn("custodian", value); self.assertNotIn("porter-a", canonical_text := json.dumps(value))
        frame = seal({"package": value}, "alice", self.depositor_keys["alice"][0], "porter-a", self.routes["porter-a"]["carriage_public_key"], "PACKAGE", unit_id(value["package"], "porter-a"))
        with self.assertRaises(NativeFrameRefused): self.custodians["porter-b"].receive(frame)
        self.assertNotIn("porter-a", canonical_text)

    def test_authenticated_cu_does_not_bypass_custodian_local_standing(self):
        value = package("alice", "harmonicdb", "hdbe.call", {"standing": True}, ttl=3600)
        wrong = {"package": value, "admission": proof("alice:porter-b", value)}
        frame = seal(wrong, "alice", self.depositor_keys["alice"][0], "porter-a", self.routes["porter-a"]["carriage_public_key"], "PACKAGE", unit_id(value["package"], "porter-a"))
        with self.assertRaises(AdmissionRefused): self.custodians["porter-a"].receive(frame)
        self.assertFalse((self.base / "porter-a/acceptances" / f"{value['package']}.json").exists())


if __name__ == "__main__": unittest.main()
