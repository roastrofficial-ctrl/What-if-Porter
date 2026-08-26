from __future__ import annotations

import hashlib
import json
import time
import uuid
from pathlib import Path

from .custody import collect_package
from .evidence_identity import EvidenceKeyHistory, sign_acceptance, verify_acceptance
from .introduction import canonical
from .lodgement import atomic_json
from .native import HEADER, open_frame, seal
from .carriage import package_digest


class PluralCarriageRefused(ValueError):
    pass


def _body(frame: bytes) -> bytes:
    if len(frame) < HEADER.size:
        raise PluralCarriageRefused("truncated plural carriage frame")
    _magic, _version, length = HEADER.unpack(frame[: HEADER.size])
    body = frame[HEADER.size :]
    if len(body) != length:
        raise PluralCarriageRefused("plural carriage frame length mismatch")
    return body


def unit_id(package_id: str, custodian: str) -> str:
    suffix = hashlib.sha256(custodian.encode()).hexdigest()[:12]
    return f"CU-PKG-{package_id}-{suffix}"


class NativeCustodian:
    """Experimental CU endpoint: custodian identity is not Package recipient."""

    def __init__(
        self,
        custodian: str,
        porter,
        carriage_private_key: str,
        depositor_public_keys: dict[str, str],
        evidence_key_fact: dict,
        evidence_private_key: str,
    ):
        self.custodian = custodian
        self.porter = porter
        self.carriage_private_key = carriage_private_key
        self.depositor_public_keys = depositor_public_keys
        self.evidence_key_fact = evidence_key_fact
        self.evidence_private_key = evidence_private_key

    def receive(self, frame: bytes) -> bytes:
        envelope, wrapped = open_frame(
            _body(frame),
            self.custodian,
            self.carriage_private_key,
            self.depositor_public_keys,
        )
        if envelope.get("class") != "PACKAGE" or not {"package"} <= set(wrapped) or set(wrapped) - {"package", "admission"}:
            raise PluralCarriageRefused("custodian accepts only Package units")
        value = wrapped["package"]
        receipt = self.porter.deposit(value, admission=wrapped.get("admission"))
        issued = max(int(time.time() * 1000), receipt["accepted_at_ms"])
        statement = sign_acceptance(
            self.porter.ipc,
            self.custodian,
            value["package"],
            self.evidence_key_fact["evidence_key"],
            self.evidence_private_key,
            issued_at_ms=issued,
        )
        origin = envelope["from"]
        return seal(
            {"receipt": receipt, "statement": statement},
            self.custodian,
            self.carriage_private_key,
            origin,
            self.depositor_public_keys[origin],
            "ACCEPTANCE_EVIDENCE",
            f"CU-EV-{value['package']}-{hashlib.sha256(self.custodian.encode()).hexdigest()[:12]}",
        )


class PluralNativeSender:
    """Depositor-local topology and retry state; no recipient-global mapping."""

    def __init__(
        self,
        identity: str,
        root: Path,
        carriage_private_key: str,
        destinations: dict[str, dict[str, dict]],
        evidence_histories: dict[str, EvidenceKeyHistory],
    ):
        self.identity = identity
        self.root = Path(root)
        self.carriage_private_key = carriage_private_key
        self.destinations = destinations
        self.evidence_histories = evidence_histories
        (self.root / "plural-native/outgoing").mkdir(parents=True, exist_ok=True)
        (self.root / "plural-native/evidence").mkdir(parents=True, exist_ok=True)

    def known_custodians(self, recipient: str) -> set[str]:
        return set(self.destinations.get(recipient, {}))

    def queue(self, value: dict, custodians: list[str] | None = None) -> list[Path]:
        available = self.destinations.get(value["to"], {})
        selected = sorted(available if custodians is None else custodians)
        if not selected or any(name not in available for name in selected):
            raise PluralCarriageRefused("depositor selected an unknown custodian")
        paths = []
        for custodian in selected:
            fact = {
                "protocol": "PORTER-PLURAL-CARRIAGE-CHECK/1",
                "unit": unit_id(value["package"], custodian),
                "class": "PACKAGE",
                "from": self.identity,
                "custodian": custodian,
                "recipient": value["to"],
                "package": value,
                "attempts": 0,
            }
            path = self.root / "plural-native/outgoing" / f"{fact['unit']}.json"
            if path.exists() and json.loads(path.read_text())["package"] != value:
                raise PluralCarriageRefused("plural CU identity names changed Package")
            if not path.exists(): atomic_json(path, fact)
            paths.append(path)
        return paths

    def deliver(self, path: Path, custodian: NativeCustodian) -> dict:
        fact = json.loads(Path(path).read_text())
        if fact["custodian"] != custodian.custodian:
            raise PluralCarriageRefused("delivery endpoint is not queued custodian")
        route = self.destinations[fact["recipient"]][fact["custodian"]]
        wrapped = {"package": fact["package"]}
        if route.get("admission_secret"):
            from .introduction import proof
            wrapped["admission"] = proof(route["admission_secret"], fact["package"])
        frame = seal(
            wrapped,
            self.identity,
            self.carriage_private_key,
            fact["custodian"],
            route["carriage_public_key"],
            "PACKAGE",
            fact["unit"],
        )
        fact["attempts"] += 1
        atomic_json(Path(path), fact)
        response = custodian.receive(frame)
        envelope, evidence = open_frame(
            _body(response),
            self.identity,
            self.carriage_private_key,
            {fact["custodian"]: route["carriage_public_key"]},
        )
        if envelope.get("class") != "ACCEPTANCE_EVIDENCE":
            raise PluralCarriageRefused("custodian returned wrong evidence class")
        verify_acceptance(
            evidence["statement"],
            self.evidence_histories[fact["custodian"]],
            expected_recipient=fact["recipient"],
            expected_package=fact["package"]["package"],
            expected_digest=package_digest(fact["package"]),
        )
        retained = {
            "protocol": "PORTER-PLURAL-CARRIAGE-CHECK/1",
            "custodian": fact["custodian"],
            "recipient": fact["recipient"],
            "package": fact["package"]["package"],
            "package_digest": package_digest(fact["package"]),
            "receipt": evidence["receipt"],
            "statement": evidence["statement"],
        }
        target = self.root / "plural-native/evidence" / f"{fact['package']['package']}--{fact['custodian']}.json"
        atomic_json(target, retained)
        Path(path).unlink()
        return retained


def host_attention_round(host_root: Path, selections: list[tuple[str, Path, str]], collector: str) -> dict:
    """One explicit Host opportunity across selected local custodian boundaries."""
    observations = []
    seen = set()
    for custodian, root, package_id in selections:
        if package_id in seen:
            observations.append({"custodian": custodian, "package": package_id, "state": "REDUNDANT_CORRESPONDENCE_SKIPPED"})
            continue
        fact = collect_package(root, package_id, collector)
        seen.add(package_id)
        observations.append({"custodian": custodian, "package": package_id, "collection": fact["collection"], "state": fact["state"]})
    value = {
        "vocabulary": "PORTER-PLURAL-ATTENTION-CHECK/1",
        "round": "RD-" + uuid.uuid4().hex,
        "host": collector,
        "observed_at_ms": int(time.time() * 1000),
        "observations": observations,
    }
    atomic_json(Path(host_root) / "plural-rounds" / f"{value['round']}.json", value)
    return value
