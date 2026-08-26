from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from porter.attestation import (
    AttestationRefused,
    NetworkObservation,
    generate_private_key,
    issue,
    measurement_root,
    observe_network_state,
    verify,
)
from porter.protocol import package


class AttestationExperiment(unittest.TestCase):
    def setUp(self):
        self.private = generate_private_key()
        self.public = measurement_root(self.private)
        self.empty = NetworkObservation((), (), (), ())

    def fact(self, nonce="challenge-one"):
        return issue("find-me", nonce, self.private, observation=self.empty, now=1000)

    def test_nonce_freshness_root_and_signature_are_verified(self):
        fact = self.fact()
        self.assertIs(fact, verify(fact, expected_host="find-me", expected_nonce="challenge-one", trusted_root=self.public, now=1001))
        for changes in ({"nonce": "replay"}, {"expires_at": 1000}, {"no_external_routes": False}):
            altered = {**fact, **changes}
            with self.assertRaises(AttestationRefused):
                verify(altered, expected_host="find-me", expected_nonce="challenge-one", trusted_root=self.public, now=1001)
        with self.assertRaisesRegex(AttestationRefused, "fresh"):
            verify(fact, expected_host="find-me", expected_nonce="challenge-one", trusted_root=self.public, now=1301)

    def test_fact_is_opaque_content_of_an_ordinary_package(self):
        fact = self.fact()
        value = package("find-me", "depositor", "porter.attestation", {"fact": fact})
        self.assertEqual(fact, value["payload"]["fact"])

    def test_listener_absence_is_not_equivalent_to_external_non_addressability(self):
        loopback_listener = NetworkObservation(("0100007F:1CF4",), (), (), ())
        fact = issue("find-me", "n", self.private, observation=loopback_listener, now=1000)
        self.assertFalse(fact["no_listeners"])
        self.assertTrue(fact["no_active_interface"])
        self.assertTrue(fact["no_external_routes"])

    def test_no_default_route_does_not_mean_no_external_route(self):
        specific_route = NetworkObservation((), ("eth0",), (), ("eth0:10.0.0.0/255.0.0.0",))
        fact = issue("find-me", "n", self.private, observation=specific_route, now=1000)
        self.assertTrue(fact["no_default_route"])
        self.assertFalse(fact["no_active_interface"])
        self.assertFalse(fact["no_external_routes"])

    def test_linux_proc_and_sys_snapshots_are_measured(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); proc = root / "proc"; sys = root / "sys"
            (proc / "net").mkdir(parents=True); (sys / "class/net/eth0").mkdir(parents=True)
            (proc / "net/tcp").write_text("header\n 0: 00000000:1CF4 00000000:0000 0A rest\n")
            (proc / "net/tcp6").write_text("header\n")
            (proc / "net/route").write_text("Iface Destination Gateway Flags RefCnt Use Metric Mask\neth0 00000000 0100000A 0003 0 0 0 00000000\n")
            (proc / "net/ipv6_route").write_text("")
            (sys / "class/net/eth0/operstate").write_text("up\n")
            observed = observe_network_state(proc, sys)
            self.assertEqual(("00000000:1CF4",), observed.tcp_listeners)
            self.assertEqual(("eth0",), observed.active_interfaces)
            self.assertEqual(observed.default_routes, observed.external_routes)


if __name__ == "__main__":
    unittest.main()
