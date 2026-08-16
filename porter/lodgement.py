from __future__ import annotations

import fcntl
import json
import os
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from .protocol import atomic_write, validate


class SimulatedInterruption(RuntimeError):
    """Test-only interruption after a named durable transition."""


def now_ms() -> int:
    return int(time.time() * 1000)


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    with temporary.open("w") as stream:
        stream.write(json.dumps(value, separators=(",", ":")) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    directory = os.open(path.parent, os.O_RDONLY)
    try: os.fsync(directory)
    finally: os.close(directory)


def atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    with temporary.open("w") as stream:
        stream.write(value)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def interrupt(point: str | None, expected: str) -> None:
    if point == expected:
        raise SimulatedInterruption(f"interrupted after {expected}")


@contextmanager
def locked_lodgement(root: Path, lodgement_id: str):
    locks = root / "lodgements" / "locks"
    locks.mkdir(parents=True, exist_ok=True)
    lock_path = locks / f"{lodgement_id}.lock"
    lock_path.touch(exist_ok=True)
    lock_path.chmod(0o666)
    stream = lock_path.open("a+")
    try:
        fcntl.flock(stream, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(stream, fcntl.LOCK_UN)
        stream.close()


def draft(package: dict, ticket_id: str | None = None, lodgement_id: str | None = None) -> dict:
    validate(package)
    ticket_id = ticket_id or f"CT-{uuid.uuid4().hex}"
    lodgement_id = lodgement_id or f"LG-{uuid.uuid4().hex}"
    lodged_at = now_ms()
    ticket = {
        "protocol": "PORTER/1",
        "ticket": ticket_id,
        "package": package["package"],
        "lodgement": lodgement_id,
        "created": package["created"],
        "expires": package["expires"],
        "abandoned": False,
        "collected_return": None,
        "events": [{"event": "LODGED", "at_ms": lodged_at, "details": {"lodgement": lodgement_id}}],
    }
    return {
        "protocol": "PORTER/1",
        "kind": "LODGEMENT",
        "lodgement": lodgement_id,
        "state": "LODGED",
        "lodged_at_ms": lodged_at,
        "ticket": ticket,
        "package": package,
    }


def publish(root: Path, value: dict) -> Path:
    accepted = root / "lodgements" / "lodged"
    accepted.mkdir(parents=True, exist_ok=True)
    target = accepted / f"{value['lodgement']}.json"
    if target.exists():
        surviving = json.loads(target.read_text())
        if surviving["ticket"]["ticket"] != value["ticket"]["ticket"] or surviving["package"] != value["package"]:
            raise ValueError("lodgement identity already names different correspondence")
        return target
    atomic_json(target, value)
    return target


def materialize(root: Path, value: dict, fail_after: str | None = None) -> dict:
    ticket = value["ticket"]
    package = value["package"]
    ticket_path = root / "tickets" / f"{ticket['ticket']}.json"
    mapping = root / "tickets" / "by-package" / package["package"]
    with locked_lodgement(root, value["lodgement"]):
        if not ticket_path.exists():
            atomic_json(ticket_path, ticket)
        interrupt(fail_after, "ticket")

        if mapping.exists():
            if mapping.read_text().strip() != ticket["ticket"]:
                raise ValueError("Package identity is associated with another Collection Ticket")
        else:
            atomic_text(mapping, ticket["ticket"] + "\n")
        interrupt(fail_after, "association")

        package_id = package["package"]
        already_carried = (root / "receipts" / f"{package_id}.json").exists()
        already_refused = (root / "refused" / f"{package_id}.json").exists()
        being_carried = (root / "outgoing" / f"{package_id}.carrying").exists()
        outgoing = root / "outgoing" / f"{package_id}.json"
        if not (already_carried or already_refused or being_carried or outgoing.exists()):
            atomic_write(root / "outgoing", package)
        interrupt(fail_after, "outgoing")
    return ticket


def lodge(ipc, package: dict, ticket_id: str | None = None, lodgement_id: str | None = None,
          fail_after: str | None = None) -> dict:
    root = Path(ipc)
    value = draft(package, ticket_id, lodgement_id)
    publish(root, value)
    interrupt(fail_after, "lodged")
    return materialize(root, value, fail_after)


def recover(ipc, fail_after: str | None = None) -> list[dict]:
    root = Path(ipc)
    recovered = []
    for path in sorted((root / "lodgements" / "lodged").glob("LG-*.json")):
        value = json.loads(path.read_text())
        recovered.append(materialize(root, value, fail_after))
    return recovered


def resolve(ipc, lodgement_id: str) -> dict:
    root = Path(ipc)
    path = root / "lodgements" / "lodged" / f"{lodgement_id}.json"
    if not path.exists():
        return {"lodgement": lodgement_id, "state": "NEVER_LODGED"}
    value = json.loads(path.read_text())
    materialize(root, value)
    return {"lodgement": lodgement_id, "state": "DEFINITELY_LODGED", "ticket": value["ticket"]["ticket"], "package": value["package"]["package"]}
