import json
import tempfile
import threading
import unittest
from pathlib import Path

from porter.custody import collect_package, custody, find_collection
from porter.daemon import Porter
from porter.lodgement import SimulatedInterruption
from porter.protocol import package
from porter.rounds import make_round
from porter.tickets import lodge


class GenerationFiveResponsibility(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); root = Path(self.temp.name)
        self.a, self.b = root / "origin", root / "recipient"
        self.value = package("sender", "recipient", "demo.work", {"work": 1}, reply_to="sender")
        self.ticket = lodge(self.a, self.value)
        self.recipient = Porter("recipient", self.b, {})
        self.sender = Porter("sender", self.a, {"recipient": "route"}, transport=lambda value, _: self.recipient.deposit(value))
        self.sender.carry_one(self.a / "outgoing" / f"{self.value['package']}.json")

    def tearDown(self): self.temp.cleanup()

    def test_collection_is_host_initiated_and_has_a_threshold(self):
        self.assertEqual(custody(self.b, self.value["package"])["current_custody"], "RECIPIENT_PORTER")
        self.assertEqual(len(list((self.b / "collections" / "facts").glob("*.json"))), 0)
        fact = collect_package(self.b, self.value["package"], "recipient-host")
        self.assertTrue(fact["collection"].startswith("CL-"))
        self.assertEqual(custody(self.b, self.value["package"])["current_custody"], "RECIPIENT_HOST")
        self.assertTrue((self.b / "acceptances" / f"{self.value['package']}.json").exists(), "acceptance history was mutated")
        self.assertFalse((self.b / "inbox" / f"{self.value['package']}.json").exists())

    def test_bastard_crash_after_threshold_loses_no_correspondence(self):
        with self.assertRaises(SimulatedInterruption):
            collect_package(self.b, self.value["package"], "recipient-host", "collection")
        collection = find_collection(self.b, self.value["package"])
        self.assertIsNotNone(collection)
        self.assertEqual(custody(self.b, self.value["package"])["current_custody"], "RECIPIENT_HOST")
        # Both byte projections may briefly exist; the immutable facts do not
        # disagree about responsibility. Restart repairs the projection.
        Porter("recipient", self.b, {})
        self.assertTrue((self.b / "collected" / f"{self.value['package']}.json").exists())
        self.assertFalse((self.b / "inbox" / f"{self.value['package']}.json").exists())
        repeated = collect_package(self.b, self.value["package"], "recipient-host")
        self.assertEqual(repeated["state"], "ALREADY_COLLECTED")
        self.assertEqual(repeated["collection"], collection["collection"])

    def test_association_reservation_before_threshold_cannot_invent_cl(self):
        with self.assertRaises(SimulatedInterruption):
            collect_package(
                self.b, self.value["package"], "recipient-host",
                "association_reservation",
            )
        self.assertEqual(custody(self.b, self.value["package"])["current_custody"], "RECIPIENT_PORTER")
        self.assertEqual(list((self.b / "collections" / "facts").glob("CL-*.json")), [])
        fact = collect_package(self.b, self.value["package"], "recipient-host")
        mapping = (self.b / "collections" / "by-package" / self.value["package"]).read_text().strip()
        self.assertEqual(mapping, fact["collection"])

    def test_every_post_threshold_projection_failure_recovers(self):
        for point in ("host_projection", "association"):
            with self.subTest(point=point):
                # Each subcase gets its own correspondence identity.
                value = package("sender", "recipient", "demo.work", {"point": point})
                self.recipient.deposit(value)
                with self.assertRaises(SimulatedInterruption): collect_package(self.b, value["package"], "recipient-host", point)
                Porter("recipient", self.b, {})
                fact = find_collection(self.b, value["package"])
                self.assertTrue((self.b / "collected" / f"{value['package']}.json").exists())
                self.assertFalse((self.b / "inbox" / f"{value['package']}.json").exists())
                self.assertEqual(custody(self.b, value["package"])["collection"], fact["collection"])

    def test_competing_collection_creates_one_boundary_fact(self):
        results = []
        threads = [threading.Thread(target=lambda: results.append(collect_package(self.b, self.value["package"], "recipient-host"))) for _ in range(2)]
        for thread in threads: thread.start()
        for thread in threads: thread.join()
        self.assertEqual({result["collection"] for result in results}, {results[0]["collection"]})
        self.assertEqual(len(list((self.b / "collections" / "facts").glob("CL-*.json"))), 1)

    def test_collection_does_not_claim_application_processing(self):
        fact = collect_package(self.b, self.value["package"], "recipient-host")
        application_commit = self.b / "application-processed" / f"{fact['collection']}.json"
        self.assertFalse(application_commit.exists())
        self.assertNotIn("processed", json.loads((self.b / "collections" / "facts" / f"{fact['collection']}.json").read_text()))

    def test_application_effect_and_commit_do_not_change_porter_truth(self):
        fact = collect_package(self.b, self.value["package"], "recipient-host")
        porter_before = custody(self.b, self.value["package"])
        application = self.b / "application"; application.mkdir()
        (application / "effect-without-commit").write_text("application reality may already have changed")
        self.assertEqual(custody(self.b, self.value["package"]), porter_before)
        (application / "commit").write_text("application-owned decision")
        self.assertEqual(custody(self.b, self.value["package"]), porter_before)
        canonical = json.loads((self.b / "collections" / "facts" / f"{fact['collection']}.json").read_text())
        self.assertNotIn("application", canonical)

    def test_origin_knowledge_does_not_change_when_recipient_collects(self):
        before = make_round(self.a, [self.ticket["ticket"]], "sender")["observations"][0]
        collect_package(self.b, self.value["package"], "recipient-host")
        after = make_round(self.a, [self.ticket["ticket"]], "sender")["observations"][0]
        self.assertEqual(before["carriage_knowledge"], "REMOTE_ACCEPTANCE_KNOWN")
        self.assertEqual(after["carriage_knowledge"], "REMOTE_ACCEPTANCE_KNOWN")
        self.assertNotIn("collection", after)


if __name__ == "__main__": unittest.main()
