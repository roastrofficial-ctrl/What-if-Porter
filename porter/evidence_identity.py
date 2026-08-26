from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from .carriage import package_digest
from .introduction import canonical

VOCABULARY = "PORTER-EVIDENCE-IDENTITY/1"
STATEMENT_VOCABULARY = "PORTER-SIGNED-CUSTODY/1"


class EvidenceIdentityRefused(ValueError):
    pass


def _identity(prefix: str, value: dict) -> str:
    return prefix + hashlib.sha256(canonical(value)).hexdigest()[:32]


def _sign(value: dict, private_key: str) -> str:
    key = Ed25519PrivateKey.from_private_bytes(base64.b64decode(private_key))
    return "ed25519:" + base64.b64encode(key.sign(canonical(value))).decode()


def _verify(value: dict, signature: str, public_key: str) -> None:
    try:
        if not signature.startswith("ed25519:"):
            raise ValueError("unknown signature algorithm")
        Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key, validate=True)).verify(
            base64.b64decode(signature.removeprefix("ed25519:"), validate=True), canonical(value)
        )
    except (ValueError, InvalidSignature) as exc:
        raise EvidenceIdentityRefused("evidence signature is invalid") from exc


def key_fact(
    continuity_private_key: str,
    porter: str,
    generation: int,
    predecessor: str | None,
    evidence_public_key: str,
    *,
    activates_at_ms: int,
    expires_at_ms: int,
) -> dict:
    if generation < 0 or (generation == 0) is not (predecessor is None) or expires_at_ms <= activates_at_ms:
        raise EvidenceIdentityRefused("invalid evidence-key generation")
    unsigned = {
        "vocabulary": VOCABULARY,
        "porter": porter,
        "generation": generation,
        "predecessor": predecessor,
        "evidence_public_key": evidence_public_key,
        "activates_at_ms": activates_at_ms,
        "expires_at_ms": expires_at_ms,
    }
    unsigned["evidence_key"] = _identity("EK-", unsigned)
    return {**unsigned, "signature": _sign(unsigned, continuity_private_key)}


class EvidenceKeyHistory:
    def __init__(self, porter: str, continuity_public_key: str, facts: list[dict]):
        self.porter, self.continuity_public_key = porter, continuity_public_key
        self.facts = {fact["evidence_key"]: self._validated(fact) for fact in facts}
        roots = [fact for fact in self.facts.values() if fact["generation"] == 0 and fact["predecessor"] is None]
        if len(roots) != 1:
            raise EvidenceIdentityRefused("evidence-key history needs one genesis")
        self.chain, current = [roots[0]], roots[0]
        while True:
            successors = [fact for fact in self.facts.values() if fact["predecessor"] == current["evidence_key"]]
            if len(successors) > 1:
                raise EvidenceIdentityRefused("evidence-key authority equivocated")
            if not successors:
                break
            successor = successors[0]
            if successor["generation"] != current["generation"] + 1:
                raise EvidenceIdentityRefused("evidence-key generation is discontinuous")
            if successor["activates_at_ms"] != current["expires_at_ms"]:
                raise EvidenceIdentityRefused("evidence-key succession has a gap or overlap")
            self.chain.append(successor); current = successor
        if len(self.chain) != len(self.facts):
            raise EvidenceIdentityRefused("evidence-key fact is not on the canonical chain")

    def _validated(self, fact: dict) -> dict:
        unsigned = {key: item for key, item in fact.items() if key != "signature"}
        body = {key: item for key, item in unsigned.items() if key != "evidence_key"}
        if fact.get("vocabulary") != VOCABULARY or fact.get("porter") != self.porter or fact.get("evidence_key") != _identity("EK-", body):
            raise EvidenceIdentityRefused("invalid evidence-key fact")
        _verify(unsigned, fact.get("signature", ""), self.continuity_public_key)
        return fact

    def key_at(self, evidence_key: str, at_ms: int) -> dict:
        fact = self.facts.get(evidence_key)
        if fact is None or not fact["activates_at_ms"] <= at_ms < fact["expires_at_ms"]:
            raise EvidenceIdentityRefused("evidence key was not valid when statement was issued")
        return fact


def sign_acceptance(root: Path, porter: str, package_id: str, evidence_key: str, evidence_private_key: str, *, issued_at_ms: int) -> dict:
    try:
        acceptance = json.loads((Path(root) / "acceptances" / f"{package_id}.json").read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidenceIdentityRefused("canonical AC does not exist") from exc
    if (
        acceptance.get("package", {}).get("package") != package_id
        or acceptance.get("package", {}).get("to") != acceptance.get("recipient")
    ):
        raise EvidenceIdentityRefused("canonical AC does not match evidence identity")
    if issued_at_ms < acceptance["accepted_at_ms"]:
        raise EvidenceIdentityRefused("acceptance statement predates canonical AC")
    unsigned = {
        "vocabulary": STATEMENT_VOCABULARY,
        "kind": "ACCEPTANCE_STATEMENT",
        "custodian": porter,
        "recipient": acceptance["recipient"],
        "evidence_key": evidence_key,
        "package": package_id,
        "package_digest": acceptance["package_digest"],
        "acceptance": acceptance["acceptance"],
        "accepted_at_ms": acceptance["accepted_at_ms"],
        "issued_at_ms": issued_at_ms,
        "state": "PORTER_ACCEPTED_RESPONSIBILITY",
    }
    unsigned["statement"] = _identity("SE-", unsigned)
    return {**unsigned, "signature": _sign(unsigned, evidence_private_key)}


def verify_acceptance(statement: dict, history: EvidenceKeyHistory, *, expected_recipient: str, expected_package: str, expected_digest: str) -> dict:
    unsigned = {key: item for key, item in statement.items() if key != "signature"}
    body = {key: item for key, item in unsigned.items() if key != "statement"}
    if (
        statement.get("vocabulary") != STATEMENT_VOCABULARY
        or statement.get("kind") != "ACCEPTANCE_STATEMENT"
        or statement.get("custodian") != history.porter
        or statement.get("recipient") != expected_recipient
        or statement.get("package") != expected_package
        or statement.get("package_digest") != expected_digest
        or statement.get("state") != "PORTER_ACCEPTED_RESPONSIBILITY"
        or statement.get("statement") != _identity("SE-", body)
    ):
        raise EvidenceIdentityRefused("acceptance statement does not match expected context")
    key = history.key_at(statement["evidence_key"], statement["issued_at_ms"])
    _verify(unsigned, statement.get("signature", ""), key["evidence_public_key"])
    return statement


def sign_possession(root: Path, porter: str, package_id: str, nonce: str, evidence_key: str, evidence_private_key: str, *, observed_at_ms: int) -> dict:
    root = Path(root)
    try:
        acceptance = json.loads((root / "acceptances" / f"{package_id}.json").read_text())
        value = json.loads((root / "inbox" / f"{package_id}.json").read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidenceIdentityRefused("Porter cannot observe current accepted bytes") from exc
    digest = package_digest(value)
    if acceptance.get("package_digest") != digest or acceptance.get("package", {}).get("to") != acceptance.get("recipient"):
        raise EvidenceIdentityRefused("current bytes do not match canonical AC")
    if observed_at_ms < acceptance["accepted_at_ms"]:
        raise EvidenceIdentityRefused("possession observation predates canonical AC")
    unsigned = {
        "vocabulary": STATEMENT_VOCABULARY,
        "kind": "POSSESSION_OBSERVATION",
        "custodian": porter,
        "recipient": acceptance["recipient"],
        "evidence_key": evidence_key,
        "package": package_id,
        "package_digest": digest,
        "acceptance": acceptance["acceptance"],
        "nonce": nonce,
        "observed_at_ms": observed_at_ms,
        "state": "SIGNER_OBSERVED_ACCEPTED_BYTES",
    }
    unsigned["statement"] = _identity("SE-", unsigned)
    return {**unsigned, "signature": _sign(unsigned, evidence_private_key)}


def verify_possession(statement: dict, history: EvidenceKeyHistory, *, expected_recipient: str, expected_package: str, expected_digest: str, expected_nonce: str) -> dict:
    unsigned = {key: item for key, item in statement.items() if key != "signature"}
    body = {key: item for key, item in unsigned.items() if key != "statement"}
    if (
        statement.get("kind") != "POSSESSION_OBSERVATION"
        or statement.get("custodian") != history.porter
        or statement.get("recipient") != expected_recipient
        or statement.get("package") != expected_package
        or statement.get("package_digest") != expected_digest
        or statement.get("nonce") != expected_nonce
        or statement.get("state") != "SIGNER_OBSERVED_ACCEPTED_BYTES"
        or statement.get("statement") != _identity("SE-", body)
    ):
        raise EvidenceIdentityRefused("possession observation does not match challenge")
    key = history.key_at(statement["evidence_key"], statement["observed_at_ms"])
    _verify(unsigned, statement.get("signature", ""), key["evidence_public_key"])
    return statement
