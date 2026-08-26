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
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

from porter.daemon import Porter
from porter.carriage import package_digest
from porter.host_runtime import HostRuntime
from porter.native import HEADER, open_frame, public_key, seal
from porter.protocol import atomic_write, package


SECRET = "high-value-signing-standing"


def keypair():
    key = X25519PrivateKey.generate(); private = base64.b64encode(key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())).decode()
    return private, public_key(private)


def free_port():
    stream = socket.socket(); stream.bind(("127.0.0.1", 0)); value = stream.getsockname()[1]; stream.close(); return value


def terms(kind):
    return {"secret": SECRET, "authority": "signing-host-policy", "kinds": [kind], "max_package_bytes": 16384, "max_outstanding_packages": 100, "max_outstanding_bytes": 1048576, "expires_at": EXPIRY}


class RecordingSigningAdapter:
    def __init__(self): self.collections = []
    def dispatch(self, dispatch_id, collection):
        self.collections.append(collection); return {"contract": "PORTER-HOST-ADAPTER/1", "dispatch": dispatch_id, "runtime_observation": "ADAPTER_RETURNED_CONTROL"}
    def close(self): pass


EXPIRY = int(time.time()) + 86400


class HighValueSigningHostPluralityExperiment(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(); self.base = Path(self.temporary.name)
        self.client_key, self.client_public = keypair(); self.client_port = free_port()
        self.keys = {name: keypair() for name in ("provider-a", "provider-b", "provider-c", "provider-d")}
        self.ports = {name: free_port() for name in self.keys}
        routes = {name: {"host": "127.0.0.1", "port": self.ports[name], "public_key": self.keys[name][1]} for name in self.keys}
        self.origin_root = self.base / "requester"
        self.origin = Porter("requester", self.origin_root, {}, relationships={"signing-host": terms("signing.result")}, require_introductions=True, native_private_key=self.client_key, native_custodian_identity="requester-custodian", native_recipient_custodians={"signing-host": ["provider-a", "provider-b", "provider-c"]}, native_rendezvous=routes, native_listen=f"127.0.0.1:{self.client_port}")
        self.c = self.make_custodian("provider-c"); self.d = self.make_custodian("provider-d")
        threading.Thread(target=self.origin.native.serve_forever, daemon=True).start(); threading.Thread(target=self.c.native.serve_forever, daemon=True).start(); time.sleep(.03)

    def make_custodian(self, name):
        return Porter("signing-host", self.base / name, {}, relationships={"requester": terms("signing.request")}, require_introductions=True, native_private_key=self.keys[name][0], native_custodian_identity=name, native_recipient_custodians={"requester": "requester-custodian"}, native_rendezvous={"requester-custodian": {"host": "127.0.0.1", "port": self.client_port, "public_key": self.client_public}}, native_listen=f"127.0.0.1:{self.ports[name]}")

    def tearDown(self):
        for porter in (self.origin, self.c, self.d):
            if porter.native: porter.native.stop()
        time.sleep(.02); self.temporary.cleanup()

    def pump(self, custodians, predicate, limit=400):
        for _ in range(limit):
            self.origin.native.tick()
            for custodian in custodians: custodian.native.tick()
            if predicate(): return
            time.sleep(.01)
        self.fail("production plural carriage did not converge")

    def malicious_b_response(self, value):
        # B can make a fully coherent claim over its authenticated channel and
        # then retain no Package at all. The sender can prove the claim arrived
        # from B; it cannot inspect B's storage to prove the claim was true.
        fake = {"protocol": "PORTER/1", "kind": "RECEIPT", "package": value["package"], "state": "REMOTE_PORTER_DURABLY_ACCEPTED", "recipient": "signing-host", "acceptance": "AC-malicious", "accepted_at_ms": 1, "package_digest": package_digest(value), "attests": "RECIPIENT_PORTER_ACCEPTED_RESPONSIBILITY"}
        frame = seal(fake, "provider-b", self.keys["provider-b"][0], "requester-custodian", self.client_public, "ACCEPTANCE_EVIDENCE", f"CU-EV-{value['package']}-malicious")
        envelope, clear = open_frame(frame[HEADER.size:], "requester-custodian", self.client_key, {"provider-b": self.keys["provider-b"][1]})
        self.origin.native.receive(envelope, clear)

    def test_disappearance_malice_replacement_and_networkless_recovery(self):
        value = package("requester", "signing-host", "signing.request", {"document_digest": "sha256:valuable", "operation": "sign"}, ttl=3600)
        package_before = json.dumps(value, sort_keys=True)
        atomic_write(self.origin_root / "outgoing", value); self.origin.native.stage_host_outgoing()

        # A has disappeared completely. B owns its configured key and makes a
        # completely valid-looking acceptance claim, but holds no Package.
        self.malicious_b_response(value)
        self.assertTrue((self.origin_root / "native/evidence/acceptances" / f"{value['package']}--provider-b.json").exists())
        self.assertFalse((self.base / "provider-b").exists())

        # C independently succeeds. B's claim does not suppress the C attempt;
        # A remains independently outstanding.
        self.pump([self.c], lambda: (self.origin_root / "native/evidence/acceptances" / f"{value['package']}--provider-c.json").exists())
        self.assertIsNotNone(self.origin.native._package_unit(value["package"], "provider-a"))
        self.assertIsNone(self.origin.native._package_unit(value["package"], "provider-b"))
        self.assertIsNone(self.origin.native._package_unit(value["package"], "provider-c"))

        # D was known but unused. Policy introduces it without touching PKG.
        self.origin.native.recipient_custodians["signing-host"] = ["provider-a", "provider-b", "provider-c", "provider-d"]
        admission = self.origin.admission.outbound_proof(value)
        self.origin.native.queue_package_custodian(value, "provider-d", admission)
        threading.Thread(target=self.d.native.serve_forever, daemon=True).start(); time.sleep(.03)
        self.pump([self.c, self.d], lambda: (self.origin_root / "native/evidence/acceptances" / f"{value['package']}--provider-d.json").exists())

        # Stop retrying vanished A without claiming that it failed or relinquished
        # custody. B already settled its attempt with a false claim. C is then
        # retired operationally and its complete store removed: every original
        # provider is gone.
        retired_a = self.origin.native.retire_package_custodian(value["package"], "provider-a", "PROVIDER_DISAPPEARED")
        self.assertEqual("DEPOSITOR_STOPPED_THIS_PHYSICAL_CARRIAGE_ATTEMPT", retired_a["attests"])
        self.origin.native.recipient_custodians["signing-host"] = ["provider-d"]
        self.c.native.stop(); time.sleep(.25)
        for path in sorted((self.base / "provider-c").rglob("*"), key=lambda item: len(item.parts), reverse=True):
            if path.is_file(): path.unlink()
            elif path.is_dir(): path.rmdir()

        # The unchanged networkless Host recovers through replacement D. It sees
        # Package/CL, not provider topology.
        adapter = RecordingSigningAdapter(); runtime = HostRuntime(ipc=self.base / "provider-d", host="signing-host", adapter=adapter, kinds={"signing.request"}, batch_size=10, idle_ms=10, journal=self.base / "provider-d/runtime.jsonl")
        self.assertEqual(1, runtime.visit()); self.assertEqual(value["package"], adapter.collections[0]["package"]["package"])
        self.assertNotIn("custodian", adapter.collections[0]["package"]); self.assertEqual(package_before, json.dumps(value, sort_keys=True))

        # New correspondence after migration uses only D and the same Host name.
        later = package("requester", "signing-host", "signing.request", {"document_digest": "sha256:later"}, ttl=3600)
        atomic_write(self.origin_root / "outgoing", later)
        self.pump([self.d], lambda: (self.origin_root / "native/evidence/acceptances" / f"{later['package']}--provider-d.json").exists())
        self.assertEqual(1, runtime.visit()); self.assertEqual(later["package"], adapter.collections[-1]["package"]["package"])

        # Restart retains custodian-indexed evidence and retired physical attempts.
        c_evidence = (self.origin_root / "native/evidence/acceptances" / f"{value['package']}--provider-c.json").read_bytes()
        d_evidence = (self.origin_root / "native/evidence/acceptances" / f"{value['package']}--provider-d.json").read_bytes()
        self.origin.native.stop(); time.sleep(.25)
        self.origin = Porter("requester", self.origin_root, {}, relationships={"signing-host": terms("signing.result")}, require_introductions=True, native_private_key=self.client_key, native_custodian_identity="requester-custodian", native_recipient_custodians={"signing-host": ["provider-d"]}, native_rendezvous={"provider-d": {"host": "127.0.0.1", "port": self.ports["provider-d"], "public_key": self.keys["provider-d"][1]}}, native_listen=f"127.0.0.1:{self.client_port}")
        self.assertEqual(c_evidence, (self.origin_root / "native/evidence/acceptances" / f"{value['package']}--provider-c.json").read_bytes())
        self.assertEqual(d_evidence, (self.origin_root / "native/evidence/acceptances" / f"{value['package']}--provider-d.json").read_bytes())
        self.assertEqual(1, len(list((self.origin_root / "native/retired").glob(f"CU-PKG-{value['package']}*.json"))))


if __name__ == "__main__": unittest.main()
