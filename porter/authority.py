from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from .introduction import canonical
from .lodgement import atomic_json


VOCABULARY = "PORTER-AUTHORITY/1"


class AuthorityEvidenceRefused(ValueError):
    pass


def _identity(prefix: str, value: dict) -> str:
    return prefix + hashlib.sha256(canonical(value)).hexdigest()[:32]


def generate_keypair() -> tuple[str, str]:
    private = Ed25519PrivateKey.generate()
    private_bytes = private.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    public_bytes = private.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    return base64.b64encode(private_bytes).decode(), base64.b64encode(public_bytes).decode()


def authority_root(
    authority: str,
    public_key: str,
    recipient: str,
    sender: str,
    genesis: str,
    genesis_terms: dict,
    *,
    generation: int = 0,
) -> dict:
    """The exact out-of-band assertion a fresh custodian must trust."""
    value = {
        "vocabulary": VOCABULARY,
        "kind": "AUTHORITY_ROOT",
        "authority": authority,
        "authority_generation": generation,
        "authority_public_key": public_key,
        "recipient": recipient,
        "sender": sender,
        "genesis": genesis,
        "genesis_terms": genesis_terms,
    }
    value["root"] = _identity("AR-", value)
    return value


def _verify_root(root: dict) -> dict:
    fields = {
        "vocabulary",
        "kind",
        "authority",
        "authority_generation",
        "authority_public_key",
        "recipient",
        "sender",
        "genesis",
        "genesis_terms",
        "root",
    }
    body = {key: item for key, item in root.items() if key != "root"} if isinstance(root, dict) else {}
    if (
        not isinstance(root, dict)
        or set(root) != fields
        or root.get("vocabulary") != VOCABULARY
        or root.get("kind") != "AUTHORITY_ROOT"
        or not isinstance(root.get("authority"), str)
        or not isinstance(root.get("authority_generation"), int)
        or root.get("authority_generation", -1) < 0
        or not isinstance(root.get("recipient"), str)
        or not isinstance(root.get("sender"), str)
        or not isinstance(root.get("genesis"), str)
        or not isinstance(root.get("genesis_terms"), dict)
        or root.get("root") != _identity("AR-", body)
    ):
        raise AuthorityEvidenceRefused("authority root is invalid")
    try:
        Ed25519PublicKey.from_public_bytes(
            base64.b64decode(root["authority_public_key"], validate=True)
        )
    except ValueError as exc:
        raise AuthorityEvidenceRefused("authority root public key is invalid") from exc
    return root


def transition(
    root: dict,
    private_key: str,
    predecessor: str,
    successor: str,
    successor_terms: dict,
    ceremony: str,
) -> dict:
    unsigned = {
        "vocabulary": VOCABULARY,
        "kind": "AUTHORITY_TRANSITION",
        "authority": root["authority"],
        "authority_generation": root["authority_generation"],
        "root": root["root"],
        "recipient": root["recipient"],
        "sender": root["sender"],
        "predecessor": predecessor,
        "successor": successor,
        "successor_terms": successor_terms,
        "ceremony": ceremony,
    }
    unsigned["transition"] = _identity("AT-", unsigned)
    try:
        signer = Ed25519PrivateKey.from_private_bytes(base64.b64decode(private_key, validate=True))
    except ValueError as exc:
        raise AuthorityEvidenceRefused("invalid authority private key") from exc
    return {
        **unsigned,
        "signature": "ed25519:" + base64.b64encode(signer.sign(canonical(unsigned))).decode(),
    }


def verify_transition(root: dict, value: dict) -> dict:
    _verify_root(root)
    fields = {
        "vocabulary",
        "kind",
        "authority",
        "authority_generation",
        "root",
        "recipient",
        "sender",
        "predecessor",
        "successor",
        "successor_terms",
        "ceremony",
        "transition",
        "signature",
    }
    if not isinstance(value, dict):
        raise AuthorityEvidenceRefused("authority transition does not match trusted scope")
    unsigned = {key: item for key, item in value.items() if key != "signature"}
    identity_body = {key: item for key, item in unsigned.items() if key != "transition"}
    if (
        not isinstance(value, dict)
        or set(value) != fields
        or value.get("vocabulary") != VOCABULARY
        or value.get("kind") != "AUTHORITY_TRANSITION"
        or value.get("authority") != root.get("authority")
        or value.get("authority_generation") != root.get("authority_generation")
        or value.get("root") != root.get("root")
        or value.get("recipient") != root.get("recipient")
        or value.get("sender") != root.get("sender")
        or not isinstance(value.get("predecessor"), str)
        or not isinstance(value.get("successor"), str)
        or value.get("predecessor") == value.get("successor")
        or not isinstance(value.get("successor_terms"), dict)
        or not isinstance(value.get("ceremony"), str)
        or value.get("transition") != _identity("AT-", identity_body)
    ):
        raise AuthorityEvidenceRefused("authority transition does not match trusted scope")
    try:
        signature = value.get("signature", "")
        if not signature.startswith("ed25519:"):
            raise ValueError("unknown signature algorithm")
        Ed25519PublicKey.from_public_bytes(
            base64.b64decode(root["authority_public_key"], validate=True)
        ).verify(
            base64.b64decode(signature.removeprefix("ed25519:"), validate=True),
            canonical(unsigned),
        )
    except (ValueError, InvalidSignature) as exc:
        raise AuthorityEvidenceRefused("authority transition signature is invalid") from exc
    return value


def derive(root: dict | None, transitions: list[dict]) -> dict:
    if root is None:
        return {"vocabulary": VOCABULARY, "state": "UNKNOWN"}
    valid = {}
    for item in transitions:
        value = verify_transition(root, item)
        identity = value["transition"]
        if identity in valid and valid[identity] != value:
            raise AuthorityEvidenceRefused("transition identity changed")
        valid[identity] = value

    by_predecessor: dict[str, list[dict]] = {}
    for value in valid.values():
        by_predecessor.setdefault(value["predecessor"], []).append(value)
    for values in by_predecessor.values():
        values.sort(key=lambda value: value["transition"])

    current = root["genesis"]
    terms = root["genesis_terms"]
    lineage = []
    known_terms = {current: terms}
    visited = set()
    while True:
        if current in visited:
            raise AuthorityEvidenceRefused("authority history cycles")
        visited.add(current)
        successors = by_predecessor.get(current, [])
        if len(successors) > 1:
            return {
                "vocabulary": VOCABULARY,
                "state": "FORKED",
                "root": root["root"],
                "predecessor": current,
                "predecessor_terms": terms,
                "branches": [
                    {
                        "transition": value["transition"],
                        "successor": value["successor"],
                        "successor_terms": value["successor_terms"],
                    }
                    for value in successors
                ],
                "lineage": lineage,
                "known_terms": {
                    **known_terms,
                    **{value["successor"]: value["successor_terms"] for value in successors},
                },
            }
        if not successors:
            break
        chosen = successors[0]
        lineage.append(chosen["transition"])
        current, terms = chosen["successor"], chosen["successor_terms"]
        known_terms[current] = terms

    used = set(lineage)
    pending = sorted(identity for identity in valid if identity not in used)
    return {
        "vocabulary": VOCABULARY,
        "state": "PENDING" if pending else "CURRENT",
        "root": root["root"],
        "current": current,
        "current_terms": terms,
        "lineage": lineage,
        "pending": pending,
        "known_terms": known_terms,
    }


class AuthorityStore:
    """Durable evidence set; projections are always reconstructed from evidence."""

    def __init__(self, path: Path, root: dict):
        self.path, self.root = Path(path), root
        self.evidence = self.path / "authority" / "transitions"
        self.evidence.mkdir(parents=True, exist_ok=True)

    def retain(self, value: dict) -> dict:
        verified = verify_transition(self.root, value)
        target = self.evidence / f"{verified['transition']}.json"
        if target.exists():
            try:
                existing = json.loads(target.read_text())
            except (OSError, json.JSONDecodeError) as exc:
                raise AuthorityEvidenceRefused("retained authority evidence is corrupt") from exc
            if existing != verified:
                raise AuthorityEvidenceRefused("retained authority evidence changed")
        else:
            atomic_json(target, verified)
        return self.knowledge()

    def transitions(self) -> list[dict]:
        values = []
        for path in sorted(self.evidence.glob("AT-*.json")):
            try:
                values.append(json.loads(path.read_text()))
            except (OSError, json.JSONDecodeError) as exc:
                raise AuthorityEvidenceRefused("retained authority evidence is corrupt") from exc
        return values

    def knowledge(self) -> dict:
        return derive(self.root, self.transitions())

    def export(self) -> list[dict]:
        return self.transitions()


def authorize_new(knowledge: dict, introduction: str, *, historical_replay: bool = False) -> str:
    if historical_replay:
        return "HISTORICAL_ACCEPTANCE_REPLAY"
    if knowledge.get("state") == "FORKED":
        raise AuthorityEvidenceRefused("known authority fork refuses new acceptance")
    if knowledge.get("state") not in {"CURRENT", "PENDING"}:
        raise AuthorityEvidenceRefused("current authority is unknown")
    if introduction != knowledge.get("current"):
        raise AuthorityEvidenceRefused("correspondence does not use locally current authority")
    return "NEW_ACCEPTANCE_AUTHORIZED"
