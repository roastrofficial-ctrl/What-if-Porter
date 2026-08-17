from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path

from .lodgement import atomic_json, now_ms


def package_digest(value: dict) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def acceptance_evidence(acceptance: dict) -> dict:
    return {
        "protocol": "PORTER/1",
        "kind": "RECEIPT",
        "package": acceptance["package"]["package"],
        "state": "REMOTE_PORTER_DURABLY_ACCEPTED",
        "recipient": acceptance["recipient"],
        "acceptance": acceptance["acceptance"],
        "accepted_at_ms": acceptance["accepted_at_ms"],
        "package_digest": acceptance["package_digest"],
        "attests": "RECIPIENT_PORTER_ACCEPTED_RESPONSIBILITY",
    }


def accept(root: Path, identity: str, package: dict) -> tuple[dict, bool]:
    """Publish the receiving Porter's canonical responsibility fact.

    The inbox is a replay-safe projection. Repeating one Package identity repeats
    evidence of the same acceptance; it does not create another correspondence.
    """
    path = root / "acceptances" / f"{package['package']}.json"
    if path.exists():
        existing = json.loads(path.read_text())
        if existing["package_digest"] != package_digest(package):
            raise ValueError("Package identity names different correspondence")
        inbox = root / "inbox" / f"{package['package']}.json"
        collected = root / "collected" / inbox.name
        if not inbox.exists() and not collected.exists():
            atomic_json(inbox, existing["package"])
        return existing, True
    value = {
        "protocol": "PORTER/1",
        "kind": "REMOTE_ACCEPTANCE",
        "acceptance": f"AC-{uuid.uuid4().hex}",
        "recipient": identity,
        "package": package,
        "package_digest": package_digest(package),
        "accepted_at_ms": now_ms(),
    }
    atomic_json(path, value)
    atomic_json(root / "inbox" / f"{package['package']}.json", package)
    return value, False


def recover_acceptances(root: Path) -> None:
    for path in sorted((root / "acceptances").glob("PKG-*.json")):
        value = json.loads(path.read_text())
        inbox = root / "inbox" / f"{value['package']['package']}.json"
        collected = root / "collected" / inbox.name
        if not inbox.exists() and not collected.exists():
            atomic_json(inbox, value["package"])


def note_attempt(root: Path, package_id: str) -> dict:
    path = root / "carriage" / f"{package_id}.json"
    value = (
        json.loads(path.read_text())
        if path.exists()
        else {
            "protocol": "PORTER/1",
            "kind": "CARRIAGE_KNOWLEDGE",
            "package": package_id,
            "knowledge": "ACCEPTANCE_UNKNOWN",
            "attempts": [],
        }
    )
    value["attempts"].append(
        {"attempt": len(value["attempts"]) + 1, "began_at_ms": now_ms()}
    )
    atomic_json(path, value)
    return value


def retain_evidence(root: Path, receipt: dict) -> dict:
    required = {
        "protocol",
        "kind",
        "package",
        "state",
        "recipient",
        "acceptance",
        "accepted_at_ms",
        "package_digest",
        "attests",
    }
    if not isinstance(receipt, dict) or not required <= receipt.keys():
        raise ValueError("transport returned no PORTER acceptance evidence")
    if (
        receipt["protocol"] != "PORTER/1"
        or receipt["kind"] != "RECEIPT"
        or receipt["state"] != "REMOTE_PORTER_DURABLY_ACCEPTED"
    ):
        raise ValueError("transport response is not durable acceptance evidence")
    knowledge_path = root / "carriage" / f"{receipt['package']}.json"
    if not knowledge_path.exists():
        raise ValueError("acceptance evidence has no local carriage attempt")
    atomic_json(root / "receipts" / f"{receipt['package']}.json", receipt)
    value = json.loads(knowledge_path.read_text())
    value["knowledge"] = "REMOTE_ACCEPTANCE_KNOWN"
    value["acceptance_evidence"] = receipt
    value["learned_at_ms"] = now_ms()
    atomic_json(knowledge_path, value)
    return value
