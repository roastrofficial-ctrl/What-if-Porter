import tempfile
import time
import unittest
from pathlib import Path

from porter.daemon import Porter
from porter.protocol import package
from porter.rounds import make_round
from porter.tickets import collect, inspect, lodge


class HostRoundsExperiment(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.ipc = Path(self.temp.name)
        self.outbound = package("find-me", "harmonicdb", "hdbe.call", {"operation": "info"}, reply_to="find-me")
        self.ticket = lodge(self.ipc, self.outbound)

    def tearDown(self):
        self.temp.cleanup()

    def return_arrives(self):
        returned = package("harmonicdb", "find-me", "porter.return", {"envelope": {"protocol": "HDBE/1", "ok": True}}, in_reply_to=self.outbound["package"])
        Porter("find-me", self.ipc, {}).deposit(returned)
        return returned

    def test_return_waits_silently_until_host_makes_round(self):
        returned = self.return_arrives()
        continuation = self.ipc / "application-continuation"
        time.sleep(.08)
        self.assertFalse(continuation.exists(), "arrival executed Host application code")
        round_value = make_round(self.ipc, [self.ticket["ticket"]], "find-me")
        observation = round_value["observations"][0]
        self.assertEqual(round_value["vocabulary"], "PORTER-ROUNDS/1")
        self.assertEqual(observation["state"], "RETURN_HELD")
        self.assertTrue((self.ipc / "rounds" / f"{round_value['round']}.json").exists())
        self.assertTrue((self.ipc / "inbox" / f"{returned['package']}.json").exists(), "Round collected a Return")
        result = collect(self.ipc, self.ticket["ticket"])
        continuation.write_text(result["return"])
        self.assertEqual(result["package"]["package"], returned["package"])
        self.assertGreaterEqual(observation["observation_latency_ms"], 70)

    def test_crash_after_observation_leaves_return_collectable(self):
        self.return_arrives()
        self.assertEqual(make_round(self.ipc, [self.ticket["ticket"]])["observations"][0]["state"], "RETURN_HELD")
        # The observing Host disappears here. A later Round still sees reality.
        self.assertEqual(make_round(self.ipc, [self.ticket["ticket"]])["observations"][0]["state"], "RETURN_HELD")
        self.assertEqual(collect(self.ipc, self.ticket["ticket"])["state"], "COLLECTED")

    def test_one_round_can_observe_many_collection_tickets(self):
        other_package = package("find-me", "harmonicdb", "hdbe.call", {"operation": "observe"}, reply_to="find-me")
        other_ticket = lodge(self.ipc, other_package)
        value = make_round(self.ipc, [self.ticket["ticket"], other_ticket["ticket"]], "find-me")
        self.assertEqual([item["state"] for item in value["observations"]], ["OUTSTANDING", "OUTSTANDING"])

    def test_crash_after_collection_does_not_claim_application_completion(self):
        self.return_arrives()
        self.assertEqual(collect(self.ipc, self.ticket["ticket"])["state"], "COLLECTED")
        application_record = self.ipc / "application-continuation"
        self.assertFalse(application_record.exists())
        replay = collect(self.ipc, self.ticket["ticket"])
        self.assertEqual(replay["state"], "ALREADY_COLLECTED")
        self.assertIsNotNone(replay["package"])


if __name__ == "__main__":
    unittest.main()
