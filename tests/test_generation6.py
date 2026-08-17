import json
import tempfile
import unittest
from pathlib import Path

from porter.custody import collect_package, custody
from porter.daemon import Porter
from porter.protocol import package
from porter.tickets import lodge


def attempted_generic_disposition(ipc: Path, package_id: str) -> str:
    """The deliberately minimal DS candidate: infer only from PORTER facts."""
    view = custody(ipc, package_id)
    if view["current_custody"] != "RECIPIENT_HOST": return "NOT_COLLECTED"
    related = []
    for path in (ipc / "lodgements" / "lodged").glob("LG-*.json"):
        value = json.loads(path.read_text())["package"]
        if value.get("in_reply_to") == package_id: related.append(value)
    return "RETURN_LODGED" if related else "APPLICATION_REALITY_UNKNOWN"


class GenerationSixApplicationDisposition(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.ipc = Path(self.temp.name)
        self.value = package("sender", "recipient", "demo.work", {"meaning": "opaque"}, reply_to="sender")
        Porter("recipient", self.ipc, {}).deposit(self.value)
        self.collection = collect_package(self.ipc, self.value["package"], "recipient-host")

    def tearDown(self): self.temp.cleanup()

    def test_porter_cannot_distinguish_contradictory_application_realities(self):
        canonical_before = custody(self.ipc, self.value["package"])
        realities = self.ipc / "application-realities"; realities.mkdir()
        for name in ("read-only", "effect-without-commit", "committed-success", "committed-failure", "deliberately-ignored"):
            (realities / name).write_text(name)
            self.assertEqual(custody(self.ipc, self.value["package"]), canonical_before)
            self.assertEqual(attempted_generic_disposition(self.ipc, self.value["package"]), "APPLICATION_REALITY_UNKNOWN")

    def test_candidate_states_require_application_definitions(self):
        proposed = {
            "PROCESSED": ["code began", "parse ended", "effect occurred", "transaction committed"],
            "COMPLETED": ["effect committed", "recovery recorded", "Return lodged"],
            "FAILED": ["invalid payload", "transient crash", "committed failure result"],
            "IGNORED": ["intentional decision", "process never scheduled", "crash before read"],
        }
        self.assertTrue(all(len(meanings) > 1 for meanings in proposed.values()))
        self.assertFalse(any(name in self.collection for name in proposed))

    def test_return_lodgement_proves_correspondence_not_disposition(self):
        success = package("recipient", "sender", "porter.return", {"application": "success"}, in_reply_to=self.value["package"])
        failure = package("recipient", "sender", "porter.return", {"application": "failure"}, in_reply_to=self.value["package"])
        lodge(self.ipc, success)
        self.assertEqual(attempted_generic_disposition(self.ipc, self.value["package"]), "RETURN_LODGED")
        lodge(self.ipc, failure)
        related = []
        for path in (self.ipc / "lodgements" / "lodged").glob("LG-*.json"):
            value = json.loads(path.read_text())["package"]
            if value.get("in_reply_to") == self.value["package"]: related.append(value["package"])
        self.assertEqual(set(related), {success["package"], failure["package"]})
        self.assertEqual(attempted_generic_disposition(self.ipc, self.value["package"]), "RETURN_LODGED")
        # PORTER preserves both relationships and cannot interpret either payload.

    def test_no_return_proves_only_no_return_lodgement(self):
        self.assertEqual(attempted_generic_disposition(self.ipc, self.value["package"]), "APPLICATION_REALITY_UNKNOWN")
        application_commit = self.ipc / "outside-porter" / "committed"
        application_commit.parent.mkdir(); application_commit.write_text("effect is real")
        self.assertEqual(attempted_generic_disposition(self.ipc, self.value["package"]), "APPLICATION_REALITY_UNKNOWN")

    def test_ds_fact_would_only_copy_an_unverified_host_assertion(self):
        assertions = ["PROCESSED", "FAILED"]
        for assertion in assertions:
            candidate = {"kind": "DISPOSITION", "package": self.value["package"], "asserted_by": "recipient-host", "state": assertion}
            self.assertEqual(candidate["package"], self.value["package"])
            self.assertNotIn("evidence", candidate)
        self.assertNotEqual(assertions[0], assertions[1])
        # Both contradictory DS candidates are equally well-formed. PORTER has
        # no communications fact with which to validate either, so DS is removed.


if __name__ == "__main__": unittest.main()
