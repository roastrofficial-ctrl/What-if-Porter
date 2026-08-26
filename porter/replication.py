from __future__ import annotations

import time

from .carriage import package_digest
from .threshold import ThresholdRefused, _identity, _sign, _verify

VOCABULARY = "PORTER-REPLICATION-CHECK/1"


def record(roster: dict, package: dict) -> dict:
    """Local replication bookkeeping; the Package remains correspondence identity."""
    body = {
        "vocabulary": VOCABULARY,
        "roster": roster["roster"],
        "package": package["package"],
        "package_digest": package_digest(package),
        "members": sorted(member["porter"] for member in roster["members"]),
        "required": roster["threshold_m"],
    }
    return {"replication": _identity("RP-", body), **body}


def custody_claim(roster: dict, replication: dict, member: str, package: dict, receipt: dict, private_key: str) -> dict:
    if member not in {item["porter"] for item in roster["members"]}:
        raise ThresholdRefused("replica is outside pinned roster")
    digest = package_digest(package)
    if (
        replication["roster"] != roster["roster"]
        or replication["package"] != package["package"]
        or replication["package_digest"] != digest
        or receipt.get("package") != package["package"]
        or receipt.get("package_digest") != digest
    ):
        raise ThresholdRefused("acceptance does not match replicated Package")
    unsigned = {
        "vocabulary": VOCABULARY,
        "kind": "REPLICA_CUSTODY_CLAIM",
        "roster": roster["roster"],
        "replication": replication["replication"],
        "porter": member,
        "package": package["package"],
        "package_digest": digest,
        "acceptance": receipt["acceptance"],
        "accepted_at_ms": receipt["accepted_at_ms"],
        "state": receipt["state"],
    }
    unsigned["claim"] = _identity("WC-", unsigned)
    return {**unsigned, "signature": _sign(unsigned, private_key)}


def reconcile(roster: dict, replication: dict, claims: list[dict], *, observed_at: int | None = None) -> dict:
    members = {item["porter"]: item for item in roster["members"]}
    accepted, conflicts, seen = [], [], set()
    for claim in claims:
        member = claim.get("porter")
        if member not in members:
            raise ThresholdRefused("replica is outside pinned roster")
        unsigned = {key: item for key, item in claim.items() if key != "signature"}
        identity_body = {key: item for key, item in unsigned.items() if key != "claim"}
        if claim.get("claim") != _identity("WC-", identity_body):
            raise ThresholdRefused("claim identity does not match content")
        _verify(unsigned, claim.get("signature", ""), members[member]["signing_key"])
        agrees = (
            claim.get("roster") == roster["roster"]
            and claim.get("replication") == replication["replication"]
            and claim.get("package") == replication["package"]
            and claim.get("package_digest") == replication["package_digest"]
            and claim.get("state") == "REMOTE_PORTER_DURABLY_ACCEPTED"
        )
        if member in seen or not agrees:
            conflicts.append(claim)
        else:
            seen.add(member)
            accepted.append(claim)
    status = "CONFLICT" if conflicts else ("CONFIRMED" if len(seen) >= replication["required"] else "INSUFFICIENT")
    body = {
        "vocabulary": VOCABULARY,
        "replication": replication["replication"],
        "roster": roster["roster"],
        "package": replication["package"],
        "package_digest": replication["package_digest"],
        "status": status,
        "required": replication["required"],
        "corroborated_by": sorted(seen),
        "claims": sorted(claim["claim"] for claim in accepted),
        "conflicts": sorted(claim["claim"] for claim in conflicts),
        "observed_at": int(time.time()) if observed_at is None else observed_at,
    }
    return {"confirmation": _identity("RC-", body), **body}


def recover(replication: dict, member: str, package: dict, collection: str) -> dict:
    """One exact recovered replica is sufficient; this does not imply processing."""
    if member not in replication["members"] or package["package"] != replication["package"] or package_digest(package) != replication["package_digest"]:
        raise ThresholdRefused("recovered bytes do not match replicated Package")
    body = {
        "vocabulary": VOCABULARY,
        "replication": replication["replication"],
        "package": replication["package"],
        "package_digest": replication["package_digest"],
        "recovered_from": member,
        "collection": collection,
    }
    return {"recovery": _identity("RR-", body), **body}
