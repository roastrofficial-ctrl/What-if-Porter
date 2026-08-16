import json
import tempfile
import unittest
from pathlib import Path

from porter.lodgement import SimulatedInterruption, lodge, recover, resolve
from porter.protocol import package


class GenerationThreeLodgement(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.ipc = Path(self.temp.name)
        self.package = package("sender", "recipient", "demo.work", {"work": 3}, reply_to="sender")

    def tearDown(self):
        self.temp.cleanup()

    def test_unpublished_draft_is_never_lodged(self):
        drafts = self.ipc / "lodgements" / "lodged"
        drafts.mkdir(parents=True)
        (drafts / ".LG-interrupted.tmp").write_text('{"incomplete":')
        answer = resolve(self.ipc, "LG-" + "0" * 32)
        self.assertEqual(answer["state"], "NEVER_LODGED")

    def test_every_post_publication_crash_recovers_definite_lodgement(self):
        for point in ("lodged", "ticket", "association", "outgoing"):
            with self.subTest(point=point), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                with self.assertRaises(SimulatedInterruption):
                    lodge(root, self.package, lodgement_id="LG-" + "1" * 32, ticket_id="CT-" + "2" * 32, fail_after=point)
                # A new Host/Porter process has only surviving filesystem facts.
                recover(root)
                answer = resolve(root, "LG-" + "1" * 32)
                self.assertEqual(answer["state"], "DEFINITELY_LODGED")
                self.assertTrue((root / "tickets" / f"{answer['ticket']}.json").exists())
                self.assertEqual((root / "tickets" / "by-package" / self.package["package"]).read_text().strip(), answer["ticket"])
                self.assertTrue((root / "outgoing" / f"{self.package['package']}.json").exists())

    def test_recovery_is_replay_safe(self):
        ticket = lodge(self.ipc, self.package)
        before = json.loads((self.ipc / "tickets" / f"{ticket['ticket']}.json").read_text())
        recover(self.ipc)
        recover(self.ipc)
        after = json.loads((self.ipc / "tickets" / f"{ticket['ticket']}.json").read_text())
        self.assertEqual(before, after)
        self.assertEqual(len(list((self.ipc / "outgoing").glob("PKG-*.json"))), 1)


if __name__ == "__main__":
    unittest.main()
