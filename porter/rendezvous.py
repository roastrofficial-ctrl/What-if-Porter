from __future__ import annotations

import base64
import argparse
import hashlib
import json
import time
from pathlib import Path

from .introduction import canonical, projection_json
from .lodgement import atomic_json

VOCABULARY = "PORTER-RENDEZVOUS/1"
MAX_EVIDENCE_BYTES = 16384


class RendezvousRefused(ValueError):
    pass


class RendezvousUnavailable(OSError):
    """The local Porter has no usable current approach for an identity."""

    def __init__(self, identity: str, knowledge: str):
        super().__init__(
            f"carriage could not use locally known rendezvous for {identity}: {knowledge}"
        )
        self.identity = identity
        self.knowledge = knowledge


def _ed25519():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
        Ed25519PublicKey,
    )

    return serialization, Ed25519PrivateKey, Ed25519PublicKey


def continuity_public_key(private_key: str) -> str:
    serialization, Ed25519PrivateKey, _ = _ed25519()
    private = Ed25519PrivateKey.from_private_bytes(base64.b64decode(private_key))
    return base64.b64encode(
        private.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
    ).decode()


def claim_identity(unsigned: dict) -> str:
    return "RV-" + hashlib.sha256(canonical(unsigned)).hexdigest()[:32]


def sign_transition(
    private_key: str,
    porter: str,
    generation: int,
    predecessor: str,
    location: dict,
    carriage_public_key: str,
    *,
    activates_at_ms: int | None = None,
    expires_at_ms: int | None = None,
    issued_at_ms: int | None = None,
) -> dict:
    _, Ed25519PrivateKey, _ = _ed25519()
    now = int(time.time() * 1000) if issued_at_ms is None else int(issued_at_ms)
    unsigned = {
        "vocabulary": VOCABULARY,
        "kind": "RENDEZVOUS_TRANSITION",
        "porter": porter,
        "generation": int(generation),
        "predecessor": predecessor,
        "location": {"host": str(location["host"]), "port": int(location["port"])},
        "carriage_public_key": carriage_public_key,
        "issued_at_ms": now,
        "activates_at_ms": now if activates_at_ms is None else int(activates_at_ms),
        "expires_at_ms": (
            now + 86_400_000 if expires_at_ms is None else int(expires_at_ms)
        ),
    }
    identity = claim_identity(unsigned)
    signature = Ed25519PrivateKey.from_private_bytes(
        base64.b64decode(private_key)
    ).sign(canonical(unsigned))
    return {
        **unsigned,
        "rendezvous": identity,
        "signature": "ed25519:" + base64.b64encode(signature).decode(),
    }


def verify_transition(value: dict, authority_public_key: str) -> dict:
    if not isinstance(value, dict) or len(canonical(value)) > MAX_EVIDENCE_BYTES:
        raise RendezvousRefused("RENDEZVOUS_EVIDENCE_INVALID")
    required = {
        "vocabulary",
        "kind",
        "rendezvous",
        "porter",
        "generation",
        "predecessor",
        "location",
        "carriage_public_key",
        "issued_at_ms",
        "activates_at_ms",
        "expires_at_ms",
        "signature",
    }
    if set(value) != required or value.get("vocabulary") != VOCABULARY:
        raise RendezvousRefused("RENDEZVOUS_EVIDENCE_INVALID")
    if value.get("kind") != "RENDEZVOUS_TRANSITION":
        raise RendezvousRefused("RENDEZVOUS_EVIDENCE_INVALID")
    unsigned = {
        key: value[key] for key in value if key not in {"rendezvous", "signature"}
    }
    if value["rendezvous"] != claim_identity(unsigned):
        raise RendezvousRefused("RENDEZVOUS_EVIDENCE_INVALID")
    location = value.get("location")
    if (
        not isinstance(value.get("porter"), str)
        or not isinstance(value.get("generation"), int)
        or value["generation"] < 1
        or not isinstance(value.get("predecessor"), str)
        or not isinstance(location, dict)
        or set(location) != {"host", "port"}
        or not isinstance(location["host"], str)
        or not location["host"]
        or not isinstance(location["port"], int)
        or not 0 < location["port"] < 65536
        or not isinstance(value.get("carriage_public_key"), str)
        or value["expires_at_ms"] <= value["activates_at_ms"]
    ):
        raise RendezvousRefused("RENDEZVOUS_EVIDENCE_INVALID")
    try:
        signature = value["signature"].removeprefix("ed25519:")
        _, _, Ed25519PublicKey = _ed25519()
        Ed25519PublicKey.from_public_bytes(
            base64.b64decode(authority_public_key)
        ).verify(base64.b64decode(signature), canonical(unsigned))
        # Validate the operational key encoding before it can become current.
        if len(base64.b64decode(value["carriage_public_key"])) != 32:
            raise ValueError("wrong carriage key size")
    except Exception as exc:
        raise RendezvousRefused("RENDEZVOUS_CONTINUITY_NOT_PROVEN") from exc
    return value


def genesis_identity(porter: str, value: dict) -> str:
    body = {
        "vocabulary": VOCABULARY,
        "kind": "LOCAL_GENESIS",
        "porter": porter,
        "generation": 0,
        "location": {"host": value["host"], "port": int(value["port"])},
        "carriage_public_key": value["public_key"],
    }
    return "RV-" + hashlib.sha256(canonical(body)).hexdigest()[:32]


class RendezvousKnowledge:
    """Durable local knowledge of peers, never a global current-state oracle."""

    def __init__(self, root: Path, configured: dict, authorities: dict | None = None):
        self.root = Path(root) / "rendezvous"
        self.authorities = authorities or {}
        self.now = lambda: int(time.time() * 1000)
        for identity, route in configured.items():
            fact = {
                "vocabulary": VOCABULARY,
                "kind": "LOCAL_GENESIS",
                "rendezvous": genesis_identity(identity, route),
                "porter": identity,
                "generation": 0,
                "predecessor": None,
                "location": {"host": route["host"], "port": int(route["port"])},
                "carriage_public_key": route["public_key"],
                "activates_at_ms": 0,
                "expires_at_ms": 2**63 - 1,
                "attests": "LOCALLY_CONFIGURED_INITIAL_RENDEZVOUS_KNOWLEDGE",
            }
            path = self.root / "facts" / f"{fact['rendezvous']}.json"
            if not path.exists():
                atomic_json(path, fact)
        self.recover()

    def _facts(self, identity: str | None = None) -> list[dict]:
        values = []
        for path in sorted((self.root / "facts").glob("RV-*.json")):
            value = json.loads(path.read_text())
            if identity is None or value["porter"] == identity:
                values.append(value)
        return values

    def recover(self) -> None:
        self.current: dict[str, dict] = {}
        self.conflicts: dict[str, list[str]] = {}
        self.next_activation_ms: int | None = None
        by_identity: dict[str, list[dict]] = {}
        for fact in self._facts():
            by_identity.setdefault(fact["porter"], []).append(fact)
        for identity, facts in by_identity.items():
            genesis = [fact for fact in facts if fact["generation"] == 0]
            if len(genesis) != 1:
                continue
            current = genesis[0]
            while True:
                successors = [
                    fact
                    for fact in facts
                    if fact.get("predecessor") == current["rendezvous"]
                    and fact["generation"] == current["generation"] + 1
                ]
                if not successors:
                    break
                if len(successors) > 1:
                    self.conflicts[identity] = sorted(
                        fact["rendezvous"] for fact in successors
                    )
                    break
                candidate = successors[0]
                if candidate["activates_at_ms"] > self.now():
                    if (
                        self.next_activation_ms is None
                        or candidate["activates_at_ms"] < self.next_activation_ms
                    ):
                        self.next_activation_ms = candidate["activates_at_ms"]
                    break
                current = candidate
            self.current[identity] = current
            self._project(identity)

    def _project(self, identity: str) -> None:
        value = self.status(identity)
        projection_json(self.root / "current" / f"{identity}.json", value)

    def status(self, identity: str) -> dict:
        fact = self.current.get(identity)
        if not fact:
            return {"porter": identity, "knowledge": "IDENTITY_NOT_KNOWN_LOCALLY"}
        if identity in self.conflicts:
            knowledge = "CONTINUITY_CONFLICT_OBSERVED"
        elif fact["expires_at_ms"] <= self.now():
            knowledge = "KNOWN_RENDEZVOUS_EXPIRED"
        else:
            knowledge = "CURRENT_RENDEZVOUS_KNOWN"
        return {
            "vocabulary": VOCABULARY,
            "porter": identity,
            "knowledge": knowledge,
            "rendezvous": fact["rendezvous"],
            "generation": fact["generation"],
            "location": fact["location"],
            "carriage_public_key": fact["carriage_public_key"],
            "expires_at_ms": fact["expires_at_ms"],
            **(
                {"conflicts": self.conflicts[identity]}
                if identity in self.conflicts
                else {}
            ),
        }

    def route(self, identity: str) -> dict:
        # Activation can cross while the process is alive; facts, not an external
        # refresh service, rebuild the projection.
        if (
            self.next_activation_ms is not None
            and self.now() >= self.next_activation_ms
        ):
            self.recover()
        status = self.status(identity)
        if status["knowledge"] != "CURRENT_RENDEZVOUS_KNOWN":
            raise RendezvousUnavailable(identity, status["knowledge"])
        return {
            **status["location"],
            "public_key": status["carriage_public_key"],
            "rendezvous": status["rendezvous"],
            "generation": status["generation"],
        }

    def accept(self, value: dict, fail_after: str | None = None) -> dict:
        identity = value.get("porter") if isinstance(value, dict) else None
        authority = self.authorities.get(identity)
        if not authority:
            raise RendezvousRefused("RENDEZVOUS_AUTHORITY_NOT_ESTABLISHED")
        verify_transition(value, authority)
        facts = {fact["rendezvous"]: fact for fact in self._facts(identity)}
        existing = facts.get(value["rendezvous"])
        if existing:
            return self.status(identity)
        predecessor = facts.get(value["predecessor"])
        if not predecessor:
            raise RendezvousRefused("RENDEZVOUS_PREDECESSOR_NOT_KNOWN")
        if value["generation"] != predecessor["generation"] + 1:
            raise RendezvousRefused("RENDEZVOUS_GENERATION_NOT_CONTIGUOUS")
        successors = [
            fact
            for fact in facts.values()
            if fact.get("predecessor") == value["predecessor"]
        ]
        atomic_json(self.root / "facts" / f"{value['rendezvous']}.json", value)
        if fail_after == "fact":
            raise RuntimeError("interrupted after rendezvous fact")
        self.recover()
        if successors:
            # A valid authority equivocated. Retain the bounded contradictory
            # history, but suspend movement rather than choosing by arrival time.
            self._project(identity)
        if fail_after == "projection":
            raise RuntimeError("interrupted after rendezvous projection")
        return self.status(identity)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Draft, queue, and inspect PORTER rendezvous continuity evidence"
    )
    parser.add_argument("--ipc", default="/ipc")
    commands = parser.add_subparsers(dest="command", required=True)
    status = commands.add_parser("status")
    status.add_argument("identity")
    sign = commands.add_parser("sign")
    sign.add_argument("--porter", required=True)
    sign.add_argument("--generation", required=True, type=int)
    sign.add_argument("--predecessor", required=True)
    sign.add_argument("--host", required=True)
    sign.add_argument("--port", required=True, type=int)
    sign.add_argument("--carriage-public-key", required=True)
    sign.add_argument("--continuity-private-key", required=True)
    sign.add_argument("--activates-at-ms", type=int)
    sign.add_argument("--expires-at-ms", type=int)
    queue = commands.add_parser("queue")
    queue.add_argument("--to", required=True)
    queue.add_argument("claim")
    args = parser.parse_args()
    root = Path(args.ipc) / "native"
    if args.command == "status":
        knowledge = RendezvousKnowledge(root, {})
        print(json.dumps(knowledge.status(args.identity), indent=2))
        return
    if args.command == "sign":
        value = sign_transition(
            args.continuity_private_key,
            args.porter,
            args.generation,
            args.predecessor,
            {"host": args.host, "port": args.port},
            args.carriage_public_key,
            activates_at_ms=args.activates_at_ms,
            expires_at_ms=args.expires_at_ms,
        )
        print(json.dumps(value, separators=(",", ":")))
        return
    value = json.loads(Path(args.claim).read_text())
    path = root / "rendezvous" / "outgoing" / f"{value['rendezvous']}--{args.to}.json"
    atomic_json(path, {"to": args.to, "claim": value, "attempts": 0})
    print(path)


if __name__ == "__main__":
    main()
