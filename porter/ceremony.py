from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import uuid
from pathlib import Path

from .introduction import canonical, relationship_fact
from .lodgement import atomic_json

VOCABULARY = "PORTER-CEREMONY/1"
MAX_WIRE_BYTES = 32768


class CeremonyRefused(ValueError):
    def __init__(self, private_reason="CEREMONY_NOT_ADMITTED"):
        super().__init__("CEREMONY_NOT_ADMITTED")
        self.public_reason = "CEREMONY_NOT_ADMITTED"
        self.private_reason = private_reason


class CeremonyInterrupted(RuntimeError):
    pass


def digest(value: dict) -> str:
    return "sha256:" + hashlib.sha256(canonical(value)).hexdigest()


def ceremony_proof(secret: str, value: dict) -> dict:
    identity = digest(value)
    signature = hmac.new(secret.encode(), identity.encode(), hashlib.sha256).hexdigest()
    return {
        "vocabulary": VOCABULARY,
        "ceremony_digest": identity,
        "proof": "hmac-sha256:" + signature,
    }


def verify(secret: str, value: dict, evidence: dict) -> bool:
    if not isinstance(evidence, dict) or evidence.get("vocabulary") != VOCABULARY:
        return False
    expected = ceremony_proof(secret, value)
    return hmac.compare_digest(
        str(evidence.get("ceremony_digest", "")), expected["ceremony_digest"]
    ) and hmac.compare_digest(str(evidence.get("proof", "")), expected["proof"])


def normalized_terms(recipient: str, sender: str, terms: dict) -> dict:
    return relationship_fact(recipient, sender, terms, "CEREMONIAL_AUTHORITY")["terms"]


def grant_id(recipient: str, origin: str) -> str:
    return "CG-" + hashlib.sha256(f"{recipient}\0{origin}".encode()).hexdigest()[:32]


def establish_grant(root: Path, recipient: str, origin: str, config: dict) -> dict:
    maximum = config.get("ceremony_terms") or normalized_terms(
        recipient, origin, config
    )
    fact = {
        "vocabulary": "PORTER-CEREMONIAL-GRANT/1",
        "grant": grant_id(recipient, origin),
        "recipient": recipient,
        "origin": origin,
        "relationship_sender": origin,
        "terms": maximum,
        "expires_at": int(config["ceremony_expires_at"]),
        "max_changes": int(config.get("ceremony_max_changes", 8)),
        "max_pending": int(config.get("ceremony_max_pending", 8)),
        "may_terminate": bool(config.get("ceremony_may_terminate", True)),
        "attests": "RECIPIENT_PORTER_ESTABLISHED_CEREMONIAL_AUTHORITY",
    }
    path = Path(root) / "ceremonies" / "grants" / f"{fact['grant']}.json"
    if path.exists():
        existing = json.loads(path.read_text())
        if existing != fact:
            raise ValueError("ceremonial grant identity names different authority")
        fact = existing
    else:
        atomic_json(path, fact)
    secret_path = Path(root) / "ceremonies" / "secrets" / fact["grant"]
    secret_path.parent.mkdir(parents=True, exist_ok=True)
    if (
        secret_path.exists()
        and secret_path.read_text().strip() != config["ceremony_secret"]
    ):
        raise ValueError("ceremonial possession material disagrees with grant")
    if not secret_path.exists():
        temporary = secret_path.with_suffix(".tmp")
        temporary.write_text(config["ceremony_secret"] + "\n")
        temporary.chmod(0o600)
        os.replace(temporary, secret_path)
    return fact


class CeremonyService:
    """Durable Porter-to-Porter evidence about recipient-local standing.

    Ceremony is addressed to the Porter itself. It creates neither AC nor CL:
    there is no Host correspondence or custody to collect. The sole security
    threshold remains the recipient-local SC published by Admission.change.
    """

    def __init__(self, root: Path, identity: str, admission, authorities: dict):
        self.root, self.identity, self.admission = Path(root), identity, admission
        self.authorities = {}
        for peer, value in authorities.items():
            if not value.get("ceremony_secret"):
                continue
            grant = establish_grant(self.root, identity, peer, value)
            self.authorities[peer] = {
                "ceremony_secret": value["ceremony_secret"],
                "ceremony_expires_at": grant["expires_at"],
                "ceremony_max_changes": grant["max_changes"],
                "ceremony_max_pending": grant["max_pending"],
                "ceremony_may_terminate": grant["may_terminate"],
                "ceremony_terms": grant["terms"],
                "grant": grant["grant"],
            }
        self.now = time.time
        for name in (
            "lodged",
            "outgoing",
            "receipts",
            "presented",
            "pending",
            "results",
        ):
            (self.root / "ceremonies" / name).mkdir(parents=True, exist_ok=True)
        for claimed in (self.root / "ceremonies" / "outgoing").glob("CM-*.carrying"):
            target = claimed.with_suffix(".json")
            if not target.exists():
                claimed.rename(target)
        self.change_counts = {}
        for path in (self.root / "introductions" / "changes").glob("IN-*.json"):
            item = json.loads(path.read_text())
            if item.get("cause", "").startswith("CM-"):
                self.change_counts[item["sender"]] = (
                    self.change_counts.get(item["sender"], 0) + 1
                )
        self.recover_origin()

    def draft(
        self,
        peer: str,
        predecessor: str,
        new_secret: str | None,
        terms: dict | None,
        reason: str,
        ceremony_id: str | None = None,
        successor_introduction: str | None = None,
    ) -> dict:
        return {
            "vocabulary": VOCABULARY,
            "ceremony": ceremony_id or f"CM-{uuid.uuid4().hex}",
            "from": self.identity,
            "to": peer,
            "sender": self.identity,
            "predecessor": predecessor,
            "successor": successor_introduction
            or (f"IN-{uuid.uuid4().hex}" if terms is not None else None),
            "replacement_secret": new_secret,
            "terms": (
                normalized_terms(peer, self.identity, terms)
                if terms is not None
                else None
            ),
            "reason": reason,
            "created_at_ms": int(self.now() * 1000),
            "attests": "ORIGIN_PORTER_REQUESTED_STANDING_RECONSIDERATION",
        }

    def lodge(self, value: dict, fail_after: str | None = None) -> dict:
        if value.get("from") != self.identity:
            raise ValueError("origin Porter cannot lodge another Porter's ceremony")
        config = self.authorities.get(value.get("to"))
        secret = config and config.get("ceremony_secret")
        if not secret:
            raise ValueError("no ceremonial authority for recipient Porter")
        fact = {
            "vocabulary": VOCABULARY,
            "kind": "CEREMONY_LODGED",
            "ceremony": value["ceremony"],
            "lodged_at_ms": int(self.now() * 1000),
            "ceremony_value": value,
            "evidence": ceremony_proof(secret, value),
        }
        path = self.root / "ceremonies" / "lodged" / f"{value['ceremony']}.json"
        if path.exists():
            existing = json.loads(path.read_text())
            if existing["ceremony_value"] != value:
                raise ValueError("ceremony identity names different evidence")
            fact = existing
        else:
            atomic_json(path, fact)
        if fail_after == "lodged":
            raise CeremonyInterrupted("interrupted after origin ceremony lodgement")
        self._materialize(fact)
        if fail_after == "outgoing":
            raise CeremonyInterrupted("interrupted after ceremony carriage projection")
        return fact

    def _materialize(self, fact: dict) -> None:
        identity = fact["ceremony"]
        if (self.root / "ceremonies" / "receipts" / f"{identity}.json").exists():
            return
        target = self.root / "ceremonies" / "outgoing" / f"{identity}.json"
        if not target.exists():
            atomic_json(
                target,
                {"ceremony": fact["ceremony_value"], "evidence": fact["evidence"]},
            )

    def recover_origin(self) -> None:
        for path in (self.root / "ceremonies" / "lodged").glob("CM-*.json"):
            self._materialize(json.loads(path.read_text()))
        for path in (self.root / "ceremonies" / "receipts").glob("CM-*.json"):
            self._apply_result(json.loads(path.read_text()))

    def _apply_result(self, result: dict) -> None:
        lodged = self.root / "ceremonies" / "lodged" / f"{result['ceremony']}.json"
        if result.get("state") == "APPLIED" and lodged.exists():
            value = json.loads(lodged.read_text())["ceremony_value"]
            self.admission.succeed_outbound(
                value["to"], result.get("successor"), value.get("replacement_secret")
            )

    def retain_result(self, result: dict) -> dict:
        if (
            result.get("vocabulary") != VOCABULARY
            or result.get("kind") != "CEREMONY_RESULT"
        ):
            raise ValueError("transport returned no ceremony result")
        target = self.root / "ceremonies" / "receipts" / f"{result['ceremony']}.json"
        if target.exists():
            existing = json.loads(target.read_text())
            if existing != result:
                raise ValueError("ceremony result changed")
            self._apply_result(existing)
            return existing
        atomic_json(target, result)
        self._apply_result(result)
        return result

    def _result(self, value: dict, state: str, change: dict | None = None) -> dict:
        result = {
            "vocabulary": VOCABULARY,
            "kind": "CEREMONY_RESULT",
            "ceremony": value["ceremony"],
            "recipient": self.identity,
            "sender": value["sender"],
            "state": state,
            "ceremony_digest": digest(value),
        }
        if change:
            result.update(
                {"change": change["change"], "successor": change.get("successor")}
            )
        return result

    def _limits_allow(self, config: dict, value: dict) -> bool:
        terms = value.get("terms")
        if terms is None:
            return bool(config.get("ceremony_may_terminate", True))
        maximum = config.get("ceremony_terms") or normalized_terms(
            self.identity, value["sender"], config
        )
        return (
            set(terms["kinds"]) <= set(maximum["kinds"])
            and terms["max_package_bytes"] <= maximum["max_package_bytes"]
            and terms["max_outstanding_packages"] <= maximum["max_outstanding_packages"]
            and terms["max_outstanding_bytes"] <= maximum["max_outstanding_bytes"]
            and terms["expires_at"] <= maximum["expires_at"]
        )

    def _valid_shape(self, value: dict) -> bool:
        return (
            isinstance(value, dict)
            and value.get("vocabulary") == VOCABULARY
            and isinstance(value.get("ceremony"), str)
            and value.get("to") == self.identity
            and value.get("sender") == value.get("from")
            and isinstance(value.get("predecessor"), str)
            and (
                (
                    value.get("terms") is None
                    and value.get("successor") is None
                    and value.get("replacement_secret") is None
                )
                or (
                    isinstance(value.get("terms"), dict)
                    and isinstance(value.get("successor"), str)
                    and isinstance(value.get("replacement_secret"), str)
                )
            )
        )

    def receive(
        self,
        value: dict,
        evidence: dict,
        fail_after: str | None = None,
        drain: bool = True,
    ) -> dict:
        if len(canonical(value)) > MAX_WIRE_BYTES or not self._valid_shape(value):
            raise CeremonyRefused("INVALID_CEREMONY")
        config = self.authorities.get(value["from"])
        if (
            not config
            or int(config.get("ceremony_expires_at", 0)) <= int(self.now())
            or not verify(config["ceremony_secret"], value, evidence)
        ):
            raise CeremonyRefused("INVALID_CEREMONIAL_AUTHORITY")
        if not self._limits_allow(config, value):
            raise CeremonyRefused("CEREMONY_OUTSIDE_LOCAL_GRANT")
        identity = value["ceremony"]
        presented = self.root / "ceremonies" / "presented" / f"{identity}.json"
        encoded = digest(value)
        for path in (
            presented,
            self.root / "ceremonies" / "pending" / f"{identity}.json",
        ):
            if path.exists() and json.loads(path.read_text())["digest"] != encoded:
                raise CeremonyRefused("CEREMONY_IDENTITY_COLLISION")
        result_path = self.root / "ceremonies" / "results" / f"{identity}.json"
        if result_path.exists():
            return json.loads(result_path.read_text())
        change_path = (
            self.root / "introductions" / "changes" / f"{value['predecessor']}.json"
        )
        if change_path.exists():
            change = json.loads(change_path.read_text())
            if change.get("cause") != identity:
                raise CeremonyRefused("STALE_CEREMONY")
            result = self._result(value, "APPLIED", change)
            atomic_json(result_path, result)
            return result
        self.admission._refresh_if_changed(value["sender"])
        current = self.admission.active.get(value["sender"])
        if not current or current["introduction"] != value["predecessor"]:
            known = (
                self.root / "introductions" / "facts" / f"{value['predecessor']}.json"
            ).exists()
            if known:
                raise CeremonyRefused("STALE_CEREMONY")
            pending = list((self.root / "ceremonies" / "pending").glob("CM-*.json"))
            if len(pending) >= int(config.get("ceremony_max_pending", 8)):
                raise CeremonyRefused("PENDING_ALLOWANCE_EXHAUSTED")
            pending_path = self.root / "ceremonies" / "pending" / f"{identity}.json"
            if not pending_path.exists():
                atomic_json(
                    pending_path,
                    {"digest": encoded, "ceremony": value, "evidence": evidence},
                )
            return self._result(value, "PENDING_PREDECESSOR")
        applied = self.change_counts.get(value["sender"], 0)
        if applied >= int(config.get("ceremony_max_changes", 8)):
            raise CeremonyRefused("CEREMONY_ALLOWANCE_EXHAUSTED")
        if not presented.exists():
            atomic_json(presented, {"digest": encoded, "ceremony": value})
        if fail_after == "received":
            raise CeremonyInterrupted(
                "interrupted after recipient retained ceremony evidence"
            )
        if fail_after == "verified":
            raise CeremonyInterrupted(
                "interrupted after ceremonial authority verification"
            )
        successor = None
        if value["terms"] is not None:
            successor = self.admission.prepare(
                value["sender"],
                value["replacement_secret"],
                value["terms"],
                "CEREMONIAL_AUTHORITY",
                value["successor"],
            )
        if fail_after == "candidate":
            raise CeremonyInterrupted("interrupted after candidate Introduction")
        change = self.admission.change(
            value["sender"],
            value["replacement_secret"],
            value["terms"],
            value["reason"],
            "CEREMONIAL_AUTHORITY",
            successor_introduction=successor and successor["introduction"],
            expected_predecessor=value["predecessor"],
            cause=identity,
        )
        self.change_counts[value["sender"]] = applied + 1
        if fail_after == "change":
            raise CeremonyInterrupted("interrupted after SC threshold")
        result = self._result(value, "APPLIED", change)
        atomic_json(result_path, result)
        (self.root / "ceremonies" / "pending" / f"{identity}.json").unlink(
            missing_ok=True
        )
        if fail_after == "result":
            raise CeremonyInterrupted("interrupted after recipient ceremony result")
        if drain:
            self.drain_pending()
        return result

    def drain_pending(self) -> None:
        progressed = True
        while progressed:
            progressed = False
            for path in sorted(
                (self.root / "ceremonies" / "pending").glob("CM-*.json")
            ):
                item = json.loads(path.read_text())
                value = item["ceremony"]
                current = self.admission.active.get(value["sender"])
                if current and current["introduction"] == value["predecessor"]:
                    self.receive(value, item["evidence"], drain=False)
                    path.unlink(missing_ok=True)
                    progressed = True
                    break
