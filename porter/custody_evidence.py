from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from .introduction import canonical

VOCABULARY = "PORTER-CUSTODY-EVIDENCE/1"


class CustodyEvidenceRefused(ValueError):
    pass


def _identity(value: dict) -> str:
    return "SA-" + hashlib.sha256(canonical(value)).hexdigest()[:32]


def sign_acceptance(root: Path, porter: str, package_id: str, private_key: str) -> dict:
    """Sign only a canonical AC already durably present in this Porter's store."""
    path = Path(root) / "acceptances" / f"{package_id}.json"
    try:
        acceptance = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise CustodyEvidenceRefused("no canonical acceptance to attest") from exc
    if (
        acceptance.get("protocol") != "PORTER/1"
        or acceptance.get("kind") != "REMOTE_ACCEPTANCE"
        or acceptance.get("recipient") != porter
        or acceptance.get("package", {}).get("package") != package_id
    ):
        raise CustodyEvidenceRefused("canonical acceptance does not match signer context")
    unsigned = {
        "vocabulary": VOCABULARY,
        "kind": "SIGNED_ACCEPTANCE",
        "porter": porter,
        "recipient": acceptance["recipient"],
        "package": package_id,
        "package_digest": acceptance["package_digest"],
        "acceptance": acceptance["acceptance"],
        "accepted_at_ms": acceptance["accepted_at_ms"],
        "state": "DURABLY_ACCEPTED_RESPONSIBILITY",
        "attests": "NAMED_PORTER_PUBLISHED_THE_BOUND_CANONICAL_AC",
    }
    unsigned["statement"] = _identity(unsigned)
    key = Ed25519PrivateKey.from_private_bytes(base64.b64decode(private_key))
    return {**unsigned, "signature": "ed25519:" + base64.b64encode(key.sign(canonical(unsigned))).decode()}


def verify_acceptance(value: dict, public_key: str, *, expected_porter: str, expected_package: str, expected_digest: str) -> dict:
    unsigned = {key: item for key, item in value.items() if key != "signature"}
    identity_body = {key: item for key, item in unsigned.items() if key != "statement"}
    if (
        value.get("vocabulary") != VOCABULARY
        or value.get("kind") != "SIGNED_ACCEPTANCE"
        or value.get("porter") != expected_porter
        or value.get("recipient") != expected_porter
        or value.get("package") != expected_package
        or value.get("package_digest") != expected_digest
        or value.get("state") != "DURABLY_ACCEPTED_RESPONSIBILITY"
        or value.get("statement") != _identity(identity_body)
    ):
        raise CustodyEvidenceRefused("signed acceptance does not match expected custody")
    try:
        signature = value.get("signature", "")
        if not signature.startswith("ed25519:"):
            raise ValueError("unknown signature algorithm")
        Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key, validate=True)).verify(
            base64.b64decode(signature.removeprefix("ed25519:"), validate=True), canonical(unsigned)
        )
    except (ValueError, InvalidSignature) as exc:
        raise CustodyEvidenceRefused("invalid signed acceptance") from exc
    return value
