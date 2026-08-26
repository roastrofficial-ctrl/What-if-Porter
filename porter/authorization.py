from __future__ import annotations

import base64
import hashlib

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from .authority import AuthorityEvidenceRefused
from .carriage import package_digest
from .introduction import canonical, package_bytes


VOCABULARY = "PORTER-AUTHORIZATION/1"


class AuthorizationRefused(ValueError):
    pass


def _identity(prefix: str, value: dict) -> str:
    return prefix + hashlib.sha256(canonical(value)).hexdigest()[:32]


def authorization_key_id(public_key: str, generation: int, sender: str, recipient: str) -> str:
    return _identity(
        "AK-",
        {
            "authorization_public_key": public_key,
            "authorization_generation": generation,
            "sender": sender,
            "recipient": recipient,
        },
    )


def sign_package(
    private_key: str,
    package: dict,
    *,
    root: str,
    introduction: str,
    authorization_key: str,
    authorization_generation: int,
) -> dict:
    unsigned = {
        "vocabulary": VOCABULARY,
        "kind": "PACKAGE_AUTHORIZATION",
        "sender": package["from"],
        "recipient": package["to"],
        "package": package["package"],
        "package_digest": package_digest(package),
        "authority_root": root,
        "introduction": introduction,
        "authorization_key": authorization_key,
        "authorization_generation": authorization_generation,
    }
    unsigned["authorization"] = _identity("PA-", unsigned)
    try:
        key = Ed25519PrivateKey.from_private_bytes(base64.b64decode(private_key, validate=True))
    except ValueError as exc:
        raise AuthorizationRefused("invalid sender authorization private key") from exc
    return {
        **unsigned,
        "signature": "ed25519:" + base64.b64encode(key.sign(canonical(unsigned))).decode(),
    }


def _terms_for(knowledge: dict, introduction: str) -> dict | None:
    known = knowledge.get("known_terms", {}).get(introduction)
    if known is not None:
        return known
    if knowledge.get("state") in {"CURRENT", "PENDING"}:
        return knowledge.get("current_terms") if knowledge.get("current") == introduction else None
    if knowledge.get("state") == "FORKED":
        if knowledge.get("predecessor") == introduction:
            return knowledge.get("predecessor_terms")
        for branch in knowledge.get("branches", []):
            if branch.get("successor") == introduction:
                return branch.get("successor_terms")
    return None


def verify_package(package: dict, evidence: dict, authority_root: dict, knowledge: dict) -> dict:
    fields = {
        "vocabulary",
        "kind",
        "sender",
        "recipient",
        "package",
        "package_digest",
        "authority_root",
        "introduction",
        "authorization_key",
        "authorization_generation",
        "authorization",
        "signature",
    }
    if not isinstance(evidence, dict) or set(evidence) != fields:
        raise AuthorizationRefused("Package authorization has invalid shape")
    unsigned = {key: value for key, value in evidence.items() if key != "signature"}
    identity_body = {key: value for key, value in unsigned.items() if key != "authorization"}
    if (
        evidence.get("vocabulary") != VOCABULARY
        or evidence.get("kind") != "PACKAGE_AUTHORIZATION"
        or evidence.get("sender") != package.get("from")
        or evidence.get("recipient") != package.get("to")
        or package.get("from") != authority_root.get("sender")
        or package.get("to") != authority_root.get("recipient")
        or evidence.get("package") != package.get("package")
        or evidence.get("package_digest") != package_digest(package)
        or evidence.get("authority_root") != authority_root.get("root")
        or knowledge.get("root") != authority_root.get("root")
        or evidence.get("authorization") != _identity("PA-", identity_body)
    ):
        raise AuthorizationRefused("Package authorization does not match exact correspondence context")
    terms = _terms_for(knowledge, evidence["introduction"])
    if terms is None:
        raise AuthorizationRefused("Package authorization names unknown Standing")
    public_key = terms.get("authorization_public_key")
    generation = terms.get("authorization_generation")
    expected_key = authorization_key_id(
        public_key, generation, package["from"], package["to"]
    ) if isinstance(public_key, str) and isinstance(generation, int) else None
    if (
        evidence.get("authorization_key") != expected_key
        or evidence.get("authorization_generation") != generation
    ):
        raise AuthorizationRefused("Package authorization key is not selected by Standing")
    try:
        signature = evidence.get("signature", "")
        if not signature.startswith("ed25519:"):
            raise ValueError("unknown signature algorithm")
        Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key, validate=True)).verify(
            base64.b64decode(signature.removeprefix("ed25519:"), validate=True),
            canonical(unsigned),
        )
    except (ValueError, InvalidSignature) as exc:
        raise AuthorizationRefused("Package authorization signature is invalid") from exc
    return {
        "vocabulary": VOCABULARY,
        "authorization": evidence["authorization"],
        "package": package["package"],
        "package_digest": evidence["package_digest"],
        "introduction": evidence["introduction"],
        "proof_state": "PACKAGE_SIGNATURE_VALID",
        "terms": terms,
    }


def evaluate_admission(
    package: dict,
    evidence: dict,
    authority_root: dict,
    knowledge: dict,
    *,
    now: int,
    outstanding_count: int = 0,
    outstanding_bytes: int = 0,
    historical_digest: str | None = None,
) -> dict:
    digest = package_digest(package)
    if historical_digest is not None:
        if historical_digest != digest:
            raise AuthorizationRefused("historical Package identity names changed correspondence")
        return {
            "proof_state": "HISTORICAL_AUTHORIZATION_NOT_REEVALUATED",
            "authority_state": knowledge.get("state", "UNKNOWN"),
            "admission": "HISTORICAL_ACCEPTANCE_REPLAY",
            "package_digest": digest,
        }
    verified = verify_package(package, evidence, authority_root, knowledge)
    if knowledge.get("state") == "FORKED":
        return {**verified, "authority_state": "FORKED", "admission": "REFUSED_AUTHORITY_FORK"}
    if knowledge.get("state") not in {"CURRENT", "PENDING"}:
        raise AuthorityEvidenceRefused("current authority is unknown")
    if verified["introduction"] != knowledge.get("current"):
        return {**verified, "authority_state": knowledge["state"], "admission": "REFUSED_STALE_AUTHORITY"}
    terms = verified["terms"]
    if package.get("kind") not in terms.get("kinds", []):
        return {**verified, "authority_state": knowledge["state"], "admission": "REFUSED_KIND"}
    size = package_bytes(package)
    if size > int(terms.get("max_package_bytes", -1)):
        return {**verified, "authority_state": knowledge["state"], "admission": "REFUSED_SIZE"}
    if int(terms.get("expires_at", 0)) <= now:
        return {**verified, "authority_state": knowledge["state"], "admission": "REFUSED_EXPIRED"}
    if outstanding_count >= int(terms.get("max_outstanding_packages", -1)):
        return {**verified, "authority_state": knowledge["state"], "admission": "REFUSED_LOCAL_COUNT"}
    if outstanding_bytes + size > int(terms.get("max_outstanding_bytes", -1)):
        return {**verified, "authority_state": knowledge["state"], "admission": "REFUSED_LOCAL_BYTES"}
    return {**verified, "authority_state": knowledge["state"], "admission": "AUTHORIZED_FOR_LOCAL_AC"}
