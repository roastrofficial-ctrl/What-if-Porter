from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from .lodgement import atomic_json

VOCABULARY = "PORTER-INTRODUCTION/1"
MAX_AUTHORITY_EVIDENCE_BYTES = 16384


class AdmissionRefused(ValueError):
    """Policy refusal before AC. It creates no recipient custody fact."""

    def __init__(self, public_reason: str = "CORRESPONDENCE_NOT_ADMITTED", private_reason: str | None = None):
        super().__init__(public_reason)
        self.public_reason = public_reason
        self.private_reason = private_reason or public_reason


def canonical(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def package_bytes(value: dict) -> int:
    return len(canonical(value))


def projection_json(path: Path, value: dict) -> None:
    """Atomically replace a rebuildable view without claiming fact durability."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f".{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(value, separators=(",", ":")) + "\n")
    os.replace(temporary, path)


def proof(secret: str, value: dict) -> dict:
    digest = hashlib.sha256(canonical(value)).hexdigest()
    signature = hmac.new(secret.encode(), digest.encode(), hashlib.sha256).hexdigest()
    return {"vocabulary": VOCABULARY, "package_digest": f"sha256:{digest}", "proof": f"hmac-sha256:{signature}"}


def verify_proof(secret: str, value: dict, evidence: dict) -> bool:
    return verify_encoded_proof(secret, canonical(value), evidence)


def verify_encoded_proof(secret: str, encoded: bytes, evidence: dict) -> bool:
    if not isinstance(evidence, dict) or evidence.get("vocabulary") != VOCABULARY:
        return False
    digest = hashlib.sha256(encoded).hexdigest()
    signature = hmac.new(secret.encode(), digest.encode(), hashlib.sha256).hexdigest()
    expected = {"package_digest":f"sha256:{digest}","proof":f"hmac-sha256:{signature}"}
    return hmac.compare_digest(str(evidence.get("package_digest", "")), expected["package_digest"]) and hmac.compare_digest(str(evidence.get("proof", "")), expected["proof"])


def relationship_id(recipient: str, sender: str) -> str:
    digest = hashlib.sha256(f"{recipient}\0{sender}".encode()).hexdigest()[:32]
    return f"IN-{digest}"


def relationship_fact(recipient: str, sender: str, terms: dict, authority: str, established_at: int | None = None) -> dict:
    return {
        "vocabulary": VOCABULARY,
        "introduction": relationship_id(recipient, sender),
        "recipient": recipient,
        "sender": sender,
        "authority": authority,
        "established_at_ms": established_at or int(time.time() * 1000),
        "terms": {
            "kinds": sorted(set(terms["kinds"])),
            "max_package_bytes": int(terms["max_package_bytes"]),
            "max_outstanding_packages": int(terms["max_outstanding_packages"]),
            "max_outstanding_bytes": int(terms["max_outstanding_bytes"]),
            "expires_at": int(terms["expires_at"]),
        },
        "attests": "RECIPIENT_PORTER_ESTABLISHED_CORRESPONDENCE_STANDING",
    }


def establish(root: Path, recipient: str, sender: str, secret: str, terms: dict, authority: str = "LOCAL_POLICY") -> dict:
    """Publish standing only after an authority adapter has verified identity.

    The adapter is intentionally outside this function. It supplies a normalized
    sender claim; PORTER chooses and persists the responsibility terms.
    """
    fact = relationship_fact(recipient, sender, terms, authority)
    target = root / "introductions" / "facts" / f"{fact['introduction']}.json"
    if target.exists():
        existing = json.loads(target.read_text())
        if existing["sender"] != sender or existing["recipient"] != recipient or existing["terms"] != fact["terms"]:
            raise ValueError("Introduction identity already names different standing")
        fact = existing
    else:
        atomic_json(target, fact)
    secret_path = root / "introductions" / "secrets" / fact["introduction"]
    secret_path.parent.mkdir(parents=True, exist_ok=True)
    if secret_path.exists() and secret_path.read_text().strip() != secret:
        raise ValueError("Introduction secret disagrees with established standing")
    if not secret_path.exists():
        temporary = secret_path.with_suffix(".tmp")
        temporary.write_text(secret + "\n"); temporary.chmod(0o600); os.replace(temporary, secret_path)
    return fact


def establish_from_claim(root: Path, recipient: str, evidence: dict, verifier, secret: str, terms: dict) -> dict:
    """Authority-neutral first contact: verify identity, then apply local terms.

    A Technical Passport adapter can implement ``verifier`` using its exported
    trust material. PORTER receives only a normalized subject and issuer; it
    never asks the claim provider to choose custody policy.
    """
    if not isinstance(evidence, dict) or len(canonical(evidence)) > MAX_AUTHORITY_EVIDENCE_BYTES:
        raise AdmissionRefused(private_reason="AUTHORITY_EVIDENCE_INVALID")
    try: claim = verifier(evidence)
    except Exception as exc: raise AdmissionRefused(private_reason="AUTHORITY_UNAVAILABLE") from exc
    if not isinstance(claim, dict) or not isinstance(claim.get("subject"), str) or not isinstance(claim.get("issuer"), str):
        raise AdmissionRefused(private_reason="AUTHORITY_EVIDENCE_INVALID")
    return establish(root, recipient, claim["subject"], secret, terms, claim["issuer"])


@contextmanager
def relationship_lock(root: Path, introduction: str):
    import fcntl
    folder = root / "introductions" / "locks"; folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{introduction}.lock"
    try:path.touch(exist_ok=False);path.chmod(0o600)
    except FileExistsError:pass
    stream = path.open("a+")
    try:
        fcntl.flock(stream, fcntl.LOCK_EX); yield
    finally:
        fcntl.flock(stream, fcntl.LOCK_UN); stream.close()


class Admission:
    def __init__(self, root: Path, recipient: str, relationships: dict, required: bool = False):
        self.root, self.recipient, self.required = Path(root), recipient, required
        self.now=time.time
        self.relationships = relationships
        self.facts = {}
        for sender, config in relationships.items():
            self.facts[sender] = establish(self.root, recipient, sender, config["secret"], config, config.get("authority", "LOCAL_POLICY"))
        self.recover()

    def recover(self) -> None:
        """Rebuild budget projections from immutable AC and CL after restart."""
        current: dict[str, dict] = {sender: {"count": 0, "bytes": 0, "admissions_since_projection": 0} for sender in self.relationships}
        collected = {path.name for path in (self.root / "collections" / "by-package").glob("PKG-*")}
        for path in (self.root / "acceptances").glob("PKG-*.json"):
            value = json.loads(path.read_text()); package = value["package"]; sender = package["from"]
            if sender in current and package["package"] not in collected:
                current[sender]["count"] += 1; current[sender]["bytes"] += package_bytes(package)
        self.current = current
        for sender, value in current.items(): self._write_current(sender, value)

    def _fact(self, sender: str) -> dict:
        if sender not in self.facts: raise AdmissionRefused(private_reason="UNKNOWN_CORRESPONDENT")
        return self.facts[sender]

    def _current_path(self, sender: str) -> Path:
        return self.root / "introductions" / "current" / f"{relationship_id(self.recipient, sender)}.json"

    def _write_current(self, sender: str, value: dict) -> None:
        projection_json(self._current_path(sender), {"vocabulary": VOCABULARY, "sender": sender, "outstanding_packages":value["count"], "outstanding_bytes":value["bytes"]})

    def _reconcile_sender(self, sender: str) -> dict:
        current={"count":0,"bytes":0,"admissions_since_projection":0}
        for path in (self.root/"acceptances").glob("PKG-*.json"):
            value=json.loads(path.read_text());package=value["package"]
            if package["from"]==sender and not (self.root/"collections"/"by-package"/package["package"]).exists():
                current["count"]+=1;current["bytes"]+=package_bytes(package)
        self.current[sender]=current;self._write_current(sender,current);return current

    @contextmanager
    def authorize(self, value: dict, evidence: dict | None):
        """Hold the relationship lock across AC and projection accounting."""
        acceptance_path=self.root/"acceptances"/f"{value['package']}.json"
        if acceptance_path.exists():
            from .carriage import package_digest
            existing=json.loads(acceptance_path.read_text())
            if existing["package_digest"]!=package_digest(value):raise ValueError("Package identity names different correspondence")
            yield {"introduction":None,"size":package_bytes(value),"repeated":True};return
        if not self.required and value["from"] not in self.relationships:
            yield None; return
        sender = value["from"]
        config = self.relationships.get(sender)
        if not config: raise AdmissionRefused(private_reason="UNKNOWN_CORRESPONDENT")
        encoded=canonical(value);size=len(encoded);terms = self._fact(sender)["terms"]
        if size > terms["max_package_bytes"]: raise AdmissionRefused(private_reason="PACKAGE_TOO_LARGE")
        if value["kind"] not in terms["kinds"]: raise AdmissionRefused(private_reason="KIND_NOT_INTRODUCED")
        if terms["expires_at"] <= int(self.now()): raise AdmissionRefused(private_reason="INTRODUCTION_EXPIRED")
        if not verify_encoded_proof(config["secret"],encoded,evidence or {}): raise AdmissionRefused(private_reason="INVALID_CARRIAGE_PROOF")
        introduction = relationship_id(self.recipient, sender)
        with relationship_lock(self.root, introduction):
            current = self.current[sender]
            package_id = value["package"]
            repeated = (self.root / "acceptances" / f"{package_id}.json").exists()
            if not repeated:
                if current["count"] >= terms["max_outstanding_packages"] or current["bytes"] + size > terms["max_outstanding_bytes"]:
                    current=self._reconcile_sender(sender)
                if current["count"] >= terms["max_outstanding_packages"] or current["bytes"] + size > terms["max_outstanding_bytes"]: raise AdmissionRefused(private_reason="CUSTODY_ALLOWANCE_EXHAUSTED")
            yield {"introduction": introduction, "size": size, "repeated": repeated}
            if not repeated:
                current["count"] += 1; current["bytes"] += size; current["admissions_since_projection"] += 1
                if current["admissions_since_projection"] >= 64:
                    self._write_current(sender,current);current["admissions_since_projection"]=0

    def outbound_proof(self, value: dict) -> dict | None:
        relationship = self.relationships.get(value["to"])
        return proof(relationship["secret"], value) if relationship else None
