from __future__ import annotations

import argparse
import base64
import hashlib
import json
import secrets
import time
from dataclasses import dataclass
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from .introduction import canonical

VOCABULARY = "PORTER-ATTESTATION/1"
MAX_NONCE_BYTES = 256
MAX_LIFETIME_SECONDS = 3600


class AttestationRefused(ValueError):
    pass


@dataclass(frozen=True)
class NetworkObservation:
    tcp_listeners: tuple[str, ...]
    active_interfaces: tuple[str, ...]
    default_routes: tuple[str, ...]
    external_routes: tuple[str, ...]

    def evidence(self) -> dict:
        return {
            "tcp_listeners": list(self.tcp_listeners),
            "active_interfaces": list(self.active_interfaces),
            "default_routes": list(self.default_routes),
            "external_routes": list(self.external_routes),
        }


def challenge() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()


def generate_private_key() -> str:
    key = Ed25519PrivateKey.generate()
    return base64.b64encode(
        key.private_bytes(
            serialization.Encoding.Raw,
            serialization.PrivateFormat.Raw,
            serialization.NoEncryption(),
        )
    ).decode()


def measurement_root(private_key: str) -> str:
    key = Ed25519PrivateKey.from_private_bytes(base64.b64decode(private_key))
    return base64.b64encode(
        key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
    ).decode()


def _ipv4(hex_value: str) -> str:
    raw = bytes.fromhex(hex_value)
    return ".".join(str(part) for part in raw[::-1])


def _tcp_listeners(path: Path) -> list[str]:
    if not path.exists():
        return []
    listeners = []
    for line in path.read_text().splitlines()[1:]:
        fields = line.split()
        if len(fields) >= 4 and fields[3] == "0A":
            listeners.append(fields[1])
    return listeners


def observe_network_state(proc: Path = Path("/proc"), sys: Path = Path("/sys")) -> NetworkObservation:
    listeners = _tcp_listeners(proc / "net/tcp") + _tcp_listeners(proc / "net/tcp6")
    active = []
    interfaces = sys / "class/net"
    if interfaces.exists():
        for interface in interfaces.iterdir():
            if interface.name == "lo":
                continue
            try:
                if (interface / "operstate").read_text().strip() == "up":
                    active.append(interface.name)
            except OSError:
                continue

    defaults, routes = [], []
    ipv4_routes = proc / "net/route"
    if ipv4_routes.exists():
        for line in ipv4_routes.read_text().splitlines()[1:]:
            fields = line.split()
            if len(fields) < 8 or fields[0] == "lo" or not (int(fields[3], 16) & 1):
                continue
            route = f"{fields[0]}:{_ipv4(fields[1])}/{_ipv4(fields[7])}"
            routes.append(route)
            if fields[1] == "00000000" and fields[7] == "00000000":
                defaults.append(route)

    ipv6_routes = proc / "net/ipv6_route"
    if ipv6_routes.exists():
        for line in ipv6_routes.read_text().splitlines():
            fields = line.split()
            if len(fields) >= 10 and fields[-1] != "lo":
                route = f"{fields[-1]}:{fields[0]}/{int(fields[1], 16)}"
                routes.append(route)
                if fields[0] == "0" * 32 and fields[1] == "00":
                    defaults.append(route)

    return NetworkObservation(
        tuple(sorted(listeners)),
        tuple(sorted(active)),
        tuple(sorted(defaults)),
        tuple(sorted(routes)),
    )


def issue(
    host: str,
    nonce: str,
    private_key: str,
    *,
    observation: NetworkObservation | None = None,
    now: int | None = None,
    lifetime: int = 300,
) -> dict:
    if not isinstance(nonce, str) or not nonce or len(nonce.encode()) > MAX_NONCE_BYTES:
        raise AttestationRefused("invalid challenge nonce")
    if not 1 <= lifetime <= MAX_LIFETIME_SECONDS:
        raise AttestationRefused("invalid attestation lifetime")
    observed = observation or observe_network_state()
    observed_at = int(time.time()) if now is None else now
    unsigned = {
        "vocabulary": VOCABULARY,
        "level": 0,
        "host": host,
        "no_listeners": not observed.tcp_listeners,
        "no_default_route": not observed.default_routes,
        "no_active_interface": not observed.active_interfaces,
        # Default-route absence alone does not establish non-addressability.
        "no_external_routes": not observed.external_routes,
        "observed_at": observed_at,
        "expires_at": observed_at + lifetime,
        "nonce": nonce,
        "measurement_root": measurement_root(private_key),
        "evidence": observed.evidence(),
    }
    unsigned["attestation"] = "AT-" + hashlib.sha256(canonical(unsigned)).hexdigest()[:32]
    key = Ed25519PrivateKey.from_private_bytes(base64.b64decode(private_key))
    signature = key.sign(canonical(unsigned))
    return {**unsigned, "signature": "ed25519:" + base64.b64encode(signature).decode()}


def verify(
    fact: dict,
    *,
    expected_host: str,
    expected_nonce: str,
    trusted_root: str,
    now: int | None = None,
) -> dict:
    required = {
        "vocabulary", "level", "attestation", "host", "no_listeners",
        "no_default_route", "no_active_interface", "no_external_routes",
        "observed_at", "expires_at", "nonce", "measurement_root", "evidence",
        "signature",
    }
    if not isinstance(fact, dict) or set(fact) != required:
        raise AttestationRefused("invalid attestation shape")
    if fact["vocabulary"] != VOCABULARY or fact["level"] != 0:
        raise AttestationRefused("unsupported attestation vocabulary or level")
    if fact["host"] != expected_host or fact["nonce"] != expected_nonce:
        raise AttestationRefused("attestation is not bound to this challenge")
    if fact["measurement_root"] != trusted_root:
        raise AttestationRefused("untrusted measurement root")
    current = int(time.time()) if now is None else now
    if not isinstance(fact["observed_at"], int) or not isinstance(fact["expires_at"], int):
        raise AttestationRefused("invalid attestation time")
    if not fact["observed_at"] <= current <= fact["expires_at"]:
        raise AttestationRefused("attestation is not currently fresh")
    if fact["expires_at"] - fact["observed_at"] > MAX_LIFETIME_SECONDS:
        raise AttestationRefused("attestation lifetime exceeds policy")
    evidence = fact["evidence"]
    evidence_keys = {"tcp_listeners", "active_interfaces", "default_routes", "external_routes"}
    if (
        not isinstance(evidence, dict)
        or set(evidence) != evidence_keys
        or any(not isinstance(evidence[key], list) for key in evidence_keys)
        or any(not isinstance(item, str) for key in evidence_keys for item in evidence[key])
        or fact["no_listeners"] is not (not evidence["tcp_listeners"])
        or fact["no_active_interface"] is not (not evidence["active_interfaces"])
        or fact["no_default_route"] is not (not evidence["default_routes"])
        or fact["no_external_routes"] is not (not evidence["external_routes"])
    ):
        raise AttestationRefused("attestation claims contradict its evidence")
    unsigned = {key: value for key, value in fact.items() if key != "signature"}
    identity_body = {key: value for key, value in unsigned.items() if key != "attestation"}
    expected_id = "AT-" + hashlib.sha256(canonical(identity_body)).hexdigest()[:32]
    if fact["attestation"] != expected_id:
        raise AttestationRefused("attestation identity does not match its content")
    try:
        if not fact["signature"].startswith("ed25519:"):
            raise ValueError("unknown signature algorithm")
        signature = base64.b64decode(fact["signature"].removeprefix("ed25519:"), validate=True)
        Ed25519PublicKey.from_public_bytes(base64.b64decode(trusted_root, validate=True)).verify(
            signature, canonical(unsigned)
        )
    except (ValueError, InvalidSignature) as exc:
        raise AttestationRefused("invalid attestation signature") from exc
    return fact


def main() -> None:
    parser = argparse.ArgumentParser(description="Issue a self-attested PORTER-ATTESTATION/1 fact")
    parser.add_argument("--host", required=True)
    parser.add_argument("--nonce", required=True)
    parser.add_argument("--private-key", required=True)
    parser.add_argument("--lifetime", type=int, default=300)
    args = parser.parse_args()
    print(json.dumps(issue(args.host, args.nonce, args.private_key, lifetime=args.lifetime), separators=(",", ":")))


if __name__ == "__main__":
    main()
