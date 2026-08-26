from __future__ import annotations

import base64
import hashlib
import json
import os
import socket
import struct
import threading
import time
import uuid
from pathlib import Path

from .carriage import package_digest
from .introduction import canonical
from .lodgement import atomic_json
from .rendezvous import VOCABULARY as RENDEZVOUS_VOCABULARY
from .rendezvous import RendezvousKnowledge

MAGIC = b"PRTR"
VERSION = 1
HEADER = struct.Struct("!4sBI")
MAX_FRAME = 524288


class NativeFrameRefused(ValueError):
    pass


def _crypto():
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric.x25519 import (
        X25519PrivateKey,
        X25519PublicKey,
    )
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF

    return hashes, serialization, X25519PrivateKey, X25519PublicKey, AESGCM, HKDF


def public_key(private_key: str) -> str:
    _, serialization, X25519PrivateKey, _, _, _ = _crypto()
    private = X25519PrivateKey.from_private_bytes(base64.b64decode(private_key))
    return base64.b64encode(
        private.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
    ).decode()


def seal(
    value: dict,
    sender: str,
    sender_private_key: str,
    recipient: str,
    recipient_public_key: str,
    unit_class: str,
    unit_id: str,
) -> bytes:
    hashes, _, X25519PrivateKey, X25519PublicKey, AESGCM, HKDF = _crypto()
    private = X25519PrivateKey.from_private_bytes(base64.b64decode(sender_private_key))
    shared = private.exchange(
        X25519PublicKey.from_public_bytes(base64.b64decode(recipient_public_key))
    )
    aad = canonical(
        {
            "protocol": "PORTER-CARRIAGE/1",
            "version": VERSION,
            "unit": unit_id,
            "class": unit_class,
            "from": sender,
            "to": recipient,
        }
    )
    key = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=b"PORTER-CARRIAGE/1\0" + aad,
    ).derive(shared)
    nonce = os.urandom(12)
    encrypted = AESGCM(key).encrypt(nonce, canonical(value), aad)
    envelope = {
        "protocol": "PORTER-CARRIAGE/1",
        "version": VERSION,
        "unit": unit_id,
        "class": unit_class,
        "from": sender,
        "to": recipient,
        "nonce": base64.b64encode(nonce).decode(),
        "ciphertext": base64.b64encode(encrypted).decode(),
    }
    body = canonical(envelope)
    if len(body) > MAX_FRAME:
        raise NativeFrameRefused("native carriage unit exceeds frame limit")
    return HEADER.pack(MAGIC, VERSION, len(body)) + body


def open_frame(
    frame: bytes, identity: str, private_key: str, peer_public_keys: dict
) -> tuple[dict, dict]:
    hashes, _, X25519PrivateKey, X25519PublicKey, AESGCM, HKDF = _crypto()
    try:
        envelope = json.loads(frame)
    except Exception as exc:
        raise NativeFrameRefused("invalid native envelope") from exc
    if (
        envelope.get("protocol") != "PORTER-CARRIAGE/1"
        or envelope.get("version") != VERSION
    ):
        raise NativeFrameRefused("unknown native carriage version")
    if envelope.get("to") != identity:
        raise NativeFrameRefused("native unit names another recipient")
    sender = envelope.get("from")
    sender_public = peer_public_keys.get(sender)
    if not sender_public:
        raise NativeFrameRefused("unknown native sender identity")
    aad = canonical(
        {
            key: envelope[key]
            for key in ("protocol", "version", "unit", "class", "from", "to")
        }
    )
    try:
        private = X25519PrivateKey.from_private_bytes(base64.b64decode(private_key))
        sender_key = X25519PublicKey.from_public_bytes(base64.b64decode(sender_public))
        shared = private.exchange(sender_key)
        key = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=b"PORTER-CARRIAGE/1\0" + aad,
        ).derive(shared)
        clear = AESGCM(key).decrypt(
            base64.b64decode(envelope["nonce"]),
            base64.b64decode(envelope["ciphertext"]),
            aad,
        )
        value = json.loads(clear)
    except Exception as exc:
        raise NativeFrameRefused("protected native unit failed authentication") from exc
    return envelope, value


def _read_exact(stream, count):
    value = b""
    while len(value) < count:
        part = stream.recv(count - len(value))
        if not part:
            raise NativeFrameRefused("truncated native frame")
        value += part
    return value


class NativeCarriage:
    def __init__(
        self,
        porter,
        private_key: str,
        rendezvous: dict,
        listen: str,
        max_frame: int = MAX_FRAME,
        custodian_identity: str | None = None,
        recipient_custodians: dict[str, str] | None = None,
        continuity_authorities: dict | None = None,
    ):
        self.porter, self.root, self.identity = (
            porter,
            porter.ipc / "native",
            custodian_identity or porter.identity,
        )
        self.served_recipient_identity = porter.identity
        self.recipient_custodians = recipient_custodians or {}
        self.private_key = private_key
        self.rendezvous = rendezvous
        self.knowledge = RendezvousKnowledge(
            self.root, rendezvous, continuity_authorities or {}
        )
        self.listen = listen
        self.max_frame = min(max_frame, MAX_FRAME)
        self.running = True
        self._slots = threading.BoundedSemaphore(32)
        for name in (
            "outgoing",
            "refused",
            "attribution",
            "evidence/acceptances",
            "evidence/refusals",
            "retired",
        ):
            (self.root / name).mkdir(parents=True, exist_ok=True)
        self._server = None

    def custodian_for(self, recipient: str) -> str:
        return self.custodians_for(recipient)[0]

    def custodians_for(self, recipient: str) -> tuple[str, ...]:
        configured = self.recipient_custodians.get(recipient, recipient)
        values = configured if isinstance(configured, list) else [configured]
        if not values or any(not isinstance(value, str) or not value for value in values):
            raise ValueError("native recipient needs at least one custodian identity")
        if len(set(values)) != len(values):
            raise ValueError("native recipient custodian identities must be distinct")
        return tuple(values)

    def package_unit_id(self, package_id: str, recipient: str, custodian: str) -> str:
        configured = self.recipient_custodians.get(recipient, recipient)
        if not isinstance(configured, list):
            return f"CU-PKG-{package_id}"
        suffix = hashlib.sha256(custodian.encode()).hexdigest()[:12]
        return f"CU-PKG-{package_id}-{suffix}"

    def queue_package_custodian(self, value: dict, custodian: str, admission: dict | None = None) -> dict:
        if custodian not in self.custodians_for(value["to"]):
            raise ValueError("custodian is not selected for Package recipient")
        return self.queue(
            "PACKAGE",
            custodian,
            {"package": value, "admission": admission},
            self.package_unit_id(value["package"], value["to"], custodian),
            True,
        )

    def retire_package_custodian(self, package_id: str, custodian: str, reason: str) -> dict:
        queued = self._package_unit(package_id, custodian)
        if queued is None:
            raise ValueError("no outstanding custodian attempt to retire")
        value = json.loads(queued.read_text())
        retired = {
            **value,
            "retired_at_ms": int(time.time() * 1000),
            "retirement_reason": reason,
            "attests": "DEPOSITOR_STOPPED_THIS_PHYSICAL_CARRIAGE_ATTEMPT",
        }
        target = self.root / "retired" / queued.name
        if target.exists() and json.loads(target.read_text()) != retired:
            raise ValueError("custodian attempt retirement changed")
        if not target.exists(): atomic_json(target, retired)
        queued.unlink()
        return retired

    def queue(
        self,
        unit_class: str,
        to: str,
        value: dict,
        unit_id: str | None = None,
        await_evidence: bool = False,
    ) -> dict:
        identity = unit_id or f"CU-{uuid.uuid4().hex}"
        fact = {
            "protocol": "PORTER-CARRIAGE/1",
            "unit": identity,
            "class": unit_class,
            "from": self.identity,
            "to": to,
            "value": value,
            "await_evidence": await_evidence,
            "attempts": 0,
            "created_at_ms": int(time.time() * 1000),
        }
        path = self.root / "outgoing" / f"{identity}.json"
        if path.exists():
            existing = json.loads(path.read_text())
            if {k: existing[k] for k in ("class", "from", "to", "value")} != {
                k: fact[k] for k in ("class", "from", "to", "value")
            }:
                raise ValueError("native Unit identity names different carriage")
            return existing
        atomic_json(path, fact)
        return fact

    def stage_host_outgoing(self) -> None:
        for path in sorted((self.porter.ipc / "outgoing").glob("PKG-*.json")):
            value = json.loads(path.read_text())
            self.porter.admission._refresh_if_changed(value["to"])
            from .carriage import note_attempt

            note_attempt(self.porter.ipc, value["package"])
            evidence = self.porter.admission.outbound_proof(value)
            for custodian in self.custodians_for(value["to"]):
                self.queue_package_custodian(value, custodian, evidence)
            path.rename(path.with_suffix(".awaiting"))
        for path in sorted(
            (self.porter.ipc / "ceremonies" / "outgoing").glob("CM-*.json")
        ):
            item = json.loads(path.read_text())
            value = item["ceremony"]
            self.queue(
                "CEREMONY", self.custodian_for(value["to"]), item, f"CU-CM-{value['ceremony']}", True
            )
            path.rename(path.with_suffix(".awaiting"))

    def tick(self) -> None:
        self.stage_host_outgoing()
        for path in sorted(
            (self.root / "rendezvous" / "outgoing").glob("RV-*.json")
        ):
            value = json.loads(path.read_text())
            try:
                self.send_rendezvous(path, value)
            except Exception as exc:
                value["last_attempt"] = "KNOWN_RECIPIENT_RENDEZVOUS_ATTEMPT_FAILED"
                value["last_error"] = type(exc).__name__
                atomic_json(path, value)
        for path in sorted((self.root / "outgoing").glob("CU-*.json")):
            # The receive thread may settle an evidence Unit after glob() but
            # before this read. Its disappearance is successful convergence,
            # not a carriage failure and must never kill the carry loop.
            try:
                value = json.loads(path.read_text())
            except FileNotFoundError:
                continue
            last = value.get("last_attempt_at_ms", 0)
            if int(time.time() * 1000) - last < 200:
                continue
            try:
                self.send(path, value)
            except Exception as exc:
                value["last_attempt"] = (
                    "AWAITING_CURRENT_RENDEZVOUS_KNOWLEDGE"
                    if hasattr(exc, "knowledge")
                    else "KNOWN_RENDEZVOUS_ATTEMPT_FAILED"
                )
                value["last_error"] = type(exc).__name__
                atomic_json(path, value)
                continue

    def send(self, path: Path, value: dict) -> None:
        target = self.knowledge.route(value["to"])
        frame = seal(
            value["value"],
            self.identity,
            self.private_key,
            value["to"],
            target["public_key"],
            value["class"],
            value["unit"],
        )
        value["attempts"] += 1
        value["last_attempt_at_ms"] = int(time.time() * 1000)
        atomic_json(path, value)
        with socket.create_connection(
            (target["host"], int(target["port"])), timeout=2
        ) as stream:
            stream.sendall(frame)
            stream.shutdown(socket.SHUT_WR)
        if not value["await_evidence"]:
            path.unlink(missing_ok=True)

    def queue_rendezvous(self, to: str, claim: dict) -> Path:
        path = (
            self.root
            / "rendezvous"
            / "outgoing"
            / f"{claim['rendezvous']}--{to}.json"
        )
        atomic_json(path, {"to": to, "claim": claim, "attempts": 0})
        return path

    def send_rendezvous(self, path: Path, value: dict) -> None:
        target = self.knowledge.route(value["to"])
        body = canonical(value["claim"])
        if len(body) > self.max_frame:
            raise NativeFrameRefused("rendezvous evidence exceeds frame limit")
        value["attempts"] += 1
        value["last_attempt_at_ms"] = int(time.time() * 1000)
        atomic_json(path, value)
        frame = HEADER.pack(MAGIC, VERSION, len(body)) + body
        with socket.create_connection(
            (target["host"], int(target["port"])), timeout=2
        ) as stream:
            stream.sendall(frame)
            stream.shutdown(socket.SHUT_WR)
        path.unlink(missing_ok=True)

    def serve_forever(self) -> None:
        host, port = self.listen.rsplit(":", 1)
        server = socket.socket()
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((host, int(port)))
        server.listen(64)
        server.settimeout(0.2)
        self._server = server
        try:
            while self.running:
                try:
                    stream, _ = server.accept()
                except socket.timeout:
                    continue
                except OSError:
                    if not self.running:
                        break
                    raise
                if not self._slots.acquire(blocking=False):
                    stream.close()
                    continue
                threading.Thread(
                    target=self._receive, args=(stream,), daemon=True
                ).start()
        finally:
            server.close()

    def stop(self) -> None:
        self.running = False
        if self._server:
            self._server.close()

    def _receive(self, stream) -> None:
        try:
            stream.settimeout(2)
            header = _read_exact(stream, HEADER.size)
            magic, version, length = HEADER.unpack(header)
            if (
                magic != MAGIC
                or version != VERSION
                or length < 2
                or length > self.max_frame
            ):
                raise NativeFrameRefused("invalid native frame header")
            body = _read_exact(stream, length)
            if stream.recv(1):
                raise NativeFrameRefused("native payload exceeds declared frame")
            possible_claim = json.loads(body)
            if possible_claim.get("vocabulary") == RENDEZVOUS_VOCABULARY:
                self.knowledge.accept(possible_claim)
                return
            self.knowledge.recover()
            peers = {
                peer: fact["carriage_public_key"]
                for peer, fact in self.knowledge.current.items()
                if self.knowledge.status(peer)["knowledge"]
                == "CURRENT_RENDEZVOUS_KNOWN"
            }
            envelope, value = open_frame(body, self.identity, self.private_key, peers)
            self.receive(envelope, value)
        except Exception:
            pass
        finally:
            stream.close()
            self._slots.release()

    def receive(self, envelope: dict, wrapped: dict) -> None:
        identity = envelope["unit"]
        unit_class = envelope["class"]
        origin = envelope["from"]
        value = wrapped
        if unit_class in {"ACCEPTANCE_EVIDENCE", "REFUSAL_EVIDENCE"}:
            package_id = value.get("package")
            queued = self._package_unit(package_id, origin)
            if queued is None:
                if self._package_units(package_id):
                    raise NativeFrameRefused("native evidence came from another custodian")
                prior = self.root / "attribution" / f"{identity}.json"
                if prior.exists() and json.loads(prior.read_text()).get("peer_custodian") == origin:
                    return
                raise NativeFrameRefused("native evidence has no matching outstanding Unit")
        elif unit_class == "CEREMONY_RESULT":
            ceremony_id = value.get("ceremony")
            queued = self.root / "outgoing" / f"CU-CM-{ceremony_id}.json"
            if not queued.exists():
                prior = self.root / "attribution" / f"{identity}.json"
                if prior.exists() and json.loads(prior.read_text()).get("peer_custodian") == origin:
                    return
                raise NativeFrameRefused("ceremony result has no matching outstanding Unit")
            if json.loads(queued.read_text()).get("to") != origin:
                raise NativeFrameRefused("ceremony result came from another custodian")
        atomic_json(
            self.root / "attribution" / f"{identity}.json",
            {
                "protocol": "PORTER-CARRIAGE-ATTRIBUTION/1",
                "unit": identity,
                "class": unit_class,
                "custodian": self.identity,
                "peer_custodian": origin,
                "observed_at_ms": int(time.time() * 1000),
            },
        )
        if unit_class == "PACKAGE":
            try:
                result = self.porter.deposit(
                    value["package"], admission=value.get("admission")
                )
                kind = "ACCEPTANCE_EVIDENCE"
            except Exception as exc:
                result = {
                    "kind": "REFUSE",
                    "reason": getattr(
                        exc, "public_reason", "CORRESPONDENCE_NOT_ADMITTED"
                    ),
                    "package": value.get("package", {}).get("package"),
                }
                kind = "REFUSAL_EVIDENCE"
            suffix = hashlib.sha256(self.identity.encode()).hexdigest()[:12]
            self.queue(kind, origin, result, f"CU-EV-{value['package']['package']}-{suffix}")
        elif unit_class == "CEREMONY":
            try:
                result = self.porter.ceremonies.receive(
                    value["ceremony"], value["evidence"]
                )
            except Exception as exc:
                result = {
                    "vocabulary": "PORTER-CEREMONY/1",
                    "kind": "CEREMONY_REFUSE",
                    "ceremony": value.get("ceremony", {}).get("ceremony"),
                    "reason": getattr(exc, "public_reason", "CEREMONY_NOT_ADMITTED"),
                }
            self.queue(
                "CEREMONY_RESULT",
                origin,
                result,
                f"CU-CR-{value['ceremony']['ceremony']}",
            )
        elif unit_class == "ACCEPTANCE_EVIDENCE":
            self._retain_custodian_acceptance(value, origin, queued)
        elif unit_class == "REFUSAL_EVIDENCE":
            self._retain_custodian_refusal(value, origin, queued)
        elif unit_class == "CEREMONY_RESULT":
            if value.get("state") == "PENDING_PREDECESSOR":
                return
            if value.get("kind") == "CEREMONY_RESULT":
                self.porter._retain_native_ceremony(value)
            (self.root / "outgoing" / f"CU-CM-{value.get('ceremony')}.json").unlink(
                missing_ok=True
            )

    def _package_unit(self, package_id: str, custodian: str) -> Path | None:
        for path in (self.root / "outgoing").glob(f"CU-PKG-{package_id}*.json"):
            try:
                value = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            if value.get("class") == "PACKAGE" and value.get("to") == custodian:
                return path
        return None

    def _package_units(self, package_id: str) -> list[Path]:
        return list((self.root / "outgoing").glob(f"CU-PKG-{package_id}*.json"))

    def _validate_custodian_receipt(self, receipt: dict, queued: Path) -> dict:
        unit = json.loads(queued.read_text())
        value = unit.get("value", {}).get("package", {})
        required = {
            "protocol", "kind", "package", "state", "recipient", "acceptance",
            "accepted_at_ms", "package_digest", "attests",
        }
        if (
            not isinstance(receipt, dict)
            or not required <= receipt.keys()
            or receipt.get("protocol") != "PORTER/1"
            or receipt.get("kind") != "RECEIPT"
            or receipt.get("state") != "REMOTE_PORTER_DURABLY_ACCEPTED"
            or receipt.get("package") != value.get("package")
            or receipt.get("recipient") != value.get("to")
            or receipt.get("package_digest") != package_digest(value)
            or receipt.get("attests") != "RECIPIENT_PORTER_ACCEPTED_RESPONSIBILITY"
            or not isinstance(receipt.get("acceptance"), str)
            or not receipt["acceptance"].startswith("AC-")
            or not isinstance(receipt.get("accepted_at_ms"), int)
        ):
            raise NativeFrameRefused("custodian acceptance does not match queued Package")
        return unit

    def _retain_custodian_acceptance(self, receipt: dict, custodian: str, queued: Path) -> None:
        unit = self._validate_custodian_receipt(receipt, queued)
        package_id = receipt["package"]
        retained = {
            "protocol": "PORTER-CUSTODIAN-EVIDENCE/1",
            "kind": "CUSTODIAN_ACCEPTANCE_KNOWN",
            "custodian": custodian,
            "unit": unit["unit"],
            "recipient": receipt["recipient"],
            "package": package_id,
            "package_digest": receipt["package_digest"],
            "receipt": receipt,
        }
        target = self.root / "evidence/acceptances" / f"{package_id}--{custodian}.json"
        if target.exists() and json.loads(target.read_text()) != retained:
            raise NativeFrameRefused("custodian changed acceptance evidence")
        if not target.exists():
            atomic_json(target, retained)
        legacy = self.porter.ipc / "receipts" / f"{package_id}.json"
        if not legacy.exists() or json.loads(legacy.read_text()) == receipt:
            self.porter._retain_native_acceptance(receipt, custodian)
        else:
            self.porter.record(
                "ADDITIONAL_REMOTE_ACCEPTANCE_KNOWN",
                package_id,
                {"recipient": receipt["recipient"], "acceptance": receipt["acceptance"], "custodian": custodian},
            )
            (self.porter.ipc / "outgoing" / f"{package_id}.awaiting").unlink(missing_ok=True)
        queued.unlink(missing_ok=True)

    def _retain_custodian_refusal(self, evidence: dict, custodian: str, queued: Path) -> None:
        unit = json.loads(queued.read_text())
        package_id = evidence.get("package")
        if package_id != unit.get("value", {}).get("package", {}).get("package"):
            raise NativeFrameRefused("custodian refusal does not match queued Package")
        retained = {
            "protocol": "PORTER-CUSTODIAN-EVIDENCE/1",
            "kind": "CUSTODIAN_REFUSAL_KNOWN",
            "custodian": custodian,
            "unit": unit["unit"],
            "recipient": unit["value"]["package"]["to"],
            "package": package_id,
            "evidence": evidence,
        }
        target = self.root / "evidence/refusals" / f"{package_id}--{custodian}.json"
        if target.exists() and json.loads(target.read_text()) != retained:
            raise NativeFrameRefused("custodian changed refusal evidence")
        if not target.exists(): atomic_json(target, retained)
        queued.unlink(missing_ok=True)
        if not self._package_units(package_id) and not list((self.root / "evidence/acceptances").glob(f"{package_id}--*.json")):
            self.porter._retain_native_refusal(evidence, custodian)
