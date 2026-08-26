from __future__ import annotations

import base64
import hashlib
import time
import uuid

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from .carriage import package_digest
from .introduction import canonical
from .protocol import package

VOCABULARY = "PORTER-THRESHOLD/1"


class ThresholdRefused(ValueError):
    pass


def generate_private_key() -> str:
    key = Ed25519PrivateKey.generate()
    return base64.b64encode(key.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )).decode()


def public_key(private_key: str) -> str:
    key = Ed25519PrivateKey.from_private_bytes(base64.b64decode(private_key))
    return base64.b64encode(key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )).decode()


def _identity(prefix: str, value: dict) -> str:
    return prefix + hashlib.sha256(canonical(value)).hexdigest()[:32]


def _sign(value: dict, private_key: str) -> str:
    key = Ed25519PrivateKey.from_private_bytes(base64.b64decode(private_key))
    return "ed25519:" + base64.b64encode(key.sign(canonical(value))).decode()


def _verify(value: dict, signature: str, key: str) -> None:
    try:
        if not signature.startswith("ed25519:"):
            raise ValueError("unknown signature algorithm")
        Ed25519PublicKey.from_public_bytes(base64.b64decode(key, validate=True)).verify(
            base64.b64decode(signature.removeprefix("ed25519:"), validate=True),
            canonical(value),
        )
    except (ValueError, InvalidSignature) as exc:
        raise ThresholdRefused("invalid threshold signature") from exc


def roster(recipient: str, members: list[dict], threshold_m: int, standing_private_key: str, *, effective_from: int | None = None) -> dict:
    if not members or not 1 <= threshold_m <= len(members):
        raise ThresholdRefused("invalid roster threshold")
    names = [member.get("porter") for member in members]
    if len(set(names)) != len(names) or any(not isinstance(name, str) or not name for name in names):
        raise ThresholdRefused("roster members must have distinct identities")
    if any(set(member) != {"porter", "endpoint", "signing_key"} for member in members):
        raise ThresholdRefused("invalid roster member")
    unsigned = {
        "vocabulary": VOCABULARY,
        "recipient": recipient,
        "members": members,
        "threshold_m": threshold_m,
        "effective_from": int(time.time()) if effective_from is None else effective_from,
    }
    unsigned["roster"] = _identity("RS-", unsigned)
    return {**unsigned, "signature": _sign(unsigned, standing_private_key)}


def verify_roster(value: dict, standing_public_key: str) -> dict:
    unsigned = {key: item for key, item in value.items() if key != "signature"}
    identity_body = {key: item for key, item in unsigned.items() if key != "roster"}
    if value.get("roster") != _identity("RS-", identity_body):
        raise ThresholdRefused("roster identity does not match content")
    _verify(unsigned, value.get("signature", ""), standing_public_key)
    # Re-run structural policy independently of the signer.
    members = value.get("members", [])
    if not members or not 1 <= value.get("threshold_m", 0) <= len(members):
        raise ThresholdRefused("invalid roster threshold")
    if len({member.get("porter") for member in members}) != len(members):
        raise ThresholdRefused("duplicate roster identity")
    return value


def draft(roster_fact: dict, sender: str, kind: str, payload: dict, *, created: int | None = None, ttl: int = 300) -> tuple[dict, list[dict]]:
    now = int(time.time()) if created is None else created
    logical = {
        "vocabulary": VOCABULARY,
        "deposit": "TD-" + uuid.uuid4().hex,
        "roster": roster_fact["roster"],
        "from": sender,
        "to": roster_fact["recipient"],
        "kind": kind,
        "created": now,
        "expires": now + ttl,
        "payload": payload,
    }
    digest = "sha256:" + hashlib.sha256(canonical(logical)).hexdigest()
    packages = []
    mappings = []
    for member in roster_fact["members"]:
        value = package(sender, roster_fact["recipient"], kind, {
            "threshold": {"deposit": logical["deposit"], "roster": logical["roster"], "logical_digest": digest},
            "content": payload,
        }, ttl=ttl)
        # Preserve the logical deposit's chosen time boundary in every constituent.
        value["created"], value["expires"] = logical["created"], logical["expires"]
        packages.append(value)
        mappings.append({"porter": member["porter"], "package": value["package"], "package_digest": package_digest(value)})
    return {**logical, "logical_digest": digest, "members": mappings}, packages


def custody_claim(roster_fact: dict, deposit: dict, member: str, constituent: dict, receipt: dict, member_private_key: str) -> dict:
    configured = {item["porter"]: item for item in roster_fact["members"]}
    mapped = {item["porter"]: item for item in deposit["members"]}
    if member not in configured or member not in mapped:
        raise ThresholdRefused("claimant is not a member of the pinned roster")
    if mapped[member]["package"] != constituent["package"] or mapped[member]["package_digest"] != package_digest(constituent):
        raise ThresholdRefused("constituent does not match threshold deposit")
    if receipt.get("package") != constituent["package"] or receipt.get("package_digest") != package_digest(constituent):
        raise ThresholdRefused("receipt does not match constituent Package")
    unsigned = {
        "vocabulary": VOCABULARY,
        "kind": "CUSTODY_CLAIM",
        "roster": roster_fact["roster"],
        "deposit": deposit["deposit"],
        "logical_digest": deposit["logical_digest"],
        "porter": member,
        "package": constituent["package"],
        "package_digest": package_digest(constituent),
        "acceptance": receipt["acceptance"],
        "accepted_at_ms": receipt["accepted_at_ms"],
        "state": receipt["state"],
    }
    unsigned["claim"] = _identity("WC-", unsigned)
    return {**unsigned, "signature": _sign(unsigned, member_private_key)}


def reconcile(roster_fact: dict, deposit: dict, claims: list[dict], *, observed_at: int | None = None) -> dict:
    members = {item["porter"]: item for item in roster_fact["members"]}
    expected_packages = {item["porter"]: item for item in deposit["members"]}
    accepted, conflicts, seen = [], [], set()
    for claim in claims:
        member = claim.get("porter")
        if member not in members:
            raise ThresholdRefused("claimant is outside pinned roster")
        unsigned = {key: item for key, item in claim.items() if key != "signature"}
        identity_body = {key: item for key, item in unsigned.items() if key != "claim"}
        if claim.get("claim") != _identity("WC-", identity_body):
            raise ThresholdRefused("claim identity does not match content")
        _verify(unsigned, claim.get("signature", ""), members[member]["signing_key"])
        expected = expected_packages[member]
        agrees = (
            claim.get("roster") == roster_fact["roster"]
            and claim.get("deposit") == deposit["deposit"]
            and claim.get("logical_digest") == deposit["logical_digest"]
            and claim.get("package") == expected["package"]
            and claim.get("package_digest") == expected["package_digest"]
            and claim.get("state") == "REMOTE_PORTER_DURABLY_ACCEPTED"
        )
        if member in seen or not agrees:
            conflicts.append(claim)
        else:
            accepted.append(claim)
            seen.add(member)
    status = "CONFLICT" if conflicts else ("CONFIRMED" if len(accepted) >= roster_fact["threshold_m"] else "INSUFFICIENT")
    body = {
        "vocabulary": VOCABULARY,
        "roster": roster_fact["roster"],
        "deposit": deposit["deposit"],
        "logical_digest": deposit["logical_digest"],
        "status": status,
        "threshold_m": roster_fact["threshold_m"],
        "corroborated_by": sorted(seen),
        "claims": sorted((claim["claim"] for claim in accepted)),
        "conflicts": sorted((claim["claim"] for claim in conflicts)),
        "observed_at": int(time.time()) if observed_at is None else observed_at,
    }
    return {"confirmation": _identity("TC-", body), **body}
