import json
import tempfile
import threading
import unittest
from pathlib import Path

from porter.daemon import Porter
from porter.protocol import atomic_write, package
from porter.rounds import make_round
from porter.tickets import inspect, lodge


class GenerationFourCarriageKnowledge(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.a, self.b = root / "a", root / "b"
        self.recipient = Porter("recipient", self.b, {})
        self.value = package("sender", "recipient", "demo.work", {"one": "correspondence"}, reply_to="sender")
        self.ticket = lodge(self.a, self.value)

    def tearDown(self): self.temp.cleanup()

    def sender(self, transport): return Porter("sender", self.a, {"recipient": "route"}, transport=transport)

    def outgoing(self): return self.a / "outgoing" / f"{self.value['package']}.json"

    def test_remote_fact_can_exist_while_sender_knowledge_is_unknown(self):
        touched = self.a / "host-executed"
        def lost_evidence(value, _):
            self.recipient.deposit(value)
            raise OSError("acceptance evidence lost")
        sender = self.sender(lost_evidence)
        with self.assertRaises(OSError): sender.carry_one(self.outgoing())

        acceptance_path = self.b / "acceptances" / f"{self.value['package']}.json"
        self.assertTrue(acceptance_path.exists(), "remote acceptance is really true")
        self.assertTrue((self.b / "inbox" / f"{self.value['package']}.json").exists())
        self.assertFalse((self.a / "receipts" / f"{self.value['package']}.json").exists())
        status = inspect(self.a, self.ticket["ticket"])
        self.assertEqual(status["carriage_knowledge"], "ACCEPTANCE_UNKNOWN")
        self.assertEqual(status["carriage_attempts"], 1)
        self.assertFalse(touched.exists(), "new Porter knowledge must not execute the Host")
        observed = make_round(self.a, [self.ticket["ticket"]], "sender")["observations"][0]
        self.assertEqual(observed["carriage_knowledge"], "ACCEPTANCE_UNKNOWN")

    def test_repeated_identity_recovers_evidence_without_new_correspondence(self):
        first_acceptance = None
        calls = 0
        def lose_once(value, _):
            nonlocal first_acceptance, calls
            calls += 1
            receipt = self.recipient.deposit(value)
            first_acceptance = first_acceptance or receipt["acceptance"]
            if calls == 1: raise OSError("lost")
            return receipt
        sender = self.sender(lose_once)
        with self.assertRaises(OSError): sender.carry_one(self.outgoing())
        sender.carry_one(self.outgoing())

        receipt = json.loads((self.a / "receipts" / f"{self.value['package']}.json").read_text())
        self.assertEqual(receipt["acceptance"], first_acceptance)
        self.assertEqual(inspect(self.a, self.ticket["ticket"])["carriage_knowledge"], "REMOTE_ACCEPTANCE_KNOWN")
        self.assertEqual(inspect(self.a, self.ticket["ticket"], False)["carriage_attempts"], 2)
        self.assertEqual(len(list((self.b / "acceptances").glob("PKG-*.json"))), 1)
        self.assertEqual(len(list((self.b / "inbox").glob("PKG-*.json"))), 1)

    def test_crash_boundaries_recover_only_durable_knowledge(self):
        sender = self.sender(lambda value, _: self.recipient.deposit(value))
        with self.assertRaises(RuntimeError): sender.carry_one(self.outgoing(), "attempt")
        restarted = self.sender(lambda value, _: self.recipient.deposit(value))
        self.assertTrue(self.outgoing().exists())
        with self.assertRaises(RuntimeError): restarted.carry_one(self.outgoing(), "response")
        self.assertEqual(inspect(self.a, self.ticket["ticket"])["carriage_knowledge"], "ACCEPTANCE_UNKNOWN")
        with self.assertRaises(RuntimeError): restarted.carry_one(self.outgoing(), "retention")
        self.assertEqual(inspect(self.a, self.ticket["ticket"])["carriage_knowledge"], "REMOTE_ACCEPTANCE_KNOWN")
        self.assertFalse(self.outgoing().exists())

    def test_acceptance_recovers_inbox_and_identity_collision_is_refused(self):
        receipt = self.recipient.deposit(self.value)
        inbox = self.b / "inbox" / f"{self.value['package']}.json"
        inbox.unlink()
        Porter("recipient", self.b, {})
        self.assertTrue(inbox.exists())
        impostor = {**self.value, "payload": {"different": True}}
        with self.assertRaisesRegex(ValueError, "different correspondence"):
            self.recipient.deposit(impostor)
        self.assertEqual(self.recipient.deposit(self.value)["acceptance"], receipt["acceptance"])

    def test_transport_response_without_evidence_cannot_become_knowledge(self):
        sender = self.sender(lambda _value, _route: {"ok": True})
        with self.assertRaisesRegex(ValueError, "no PORTER acceptance evidence"):
            sender.carry_one(self.outgoing())
        self.assertEqual(inspect(self.a, self.ticket["ticket"])["carriage_knowledge"], "ACCEPTANCE_UNKNOWN")

    def test_absence_and_delay_change_no_claim_until_evidence_is_retained(self):
        sender = self.sender(lambda _value, _route: (_ for _ in ()).throw(ConnectionError("recipient absent")))
        with self.assertRaises(ConnectionError): sender.carry_one(self.outgoing())
        self.assertEqual(inspect(self.a, self.ticket["ticket"])["carriage_knowledge"], "ACCEPTANCE_UNKNOWN")

        entered = threading.Event()
        release = threading.Event()
        def delayed(value, _):
            entered.set(); release.wait(2)
            return self.recipient.deposit(value)
        sender.transport = delayed
        result = []
        thread = threading.Thread(target=lambda: result.append(sender.carry_one(self.outgoing())))
        thread.start(); self.assertTrue(entered.wait(1))
        self.assertFalse((self.a / "receipts" / f"{self.value['package']}.json").exists())
        self.assertEqual(inspect(self.a, self.ticket["ticket"])["carriage_knowledge"], "ACCEPTANCE_UNKNOWN")
        release.set(); thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(result[0]["knowledge"], "REMOTE_ACCEPTANCE_KNOWN")


if __name__ == "__main__": unittest.main()
