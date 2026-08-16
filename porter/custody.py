from __future__ import annotations

import fcntl
import json
import uuid
from contextlib import contextmanager
from pathlib import Path

from .lodgement import atomic_json, atomic_text, interrupt, now_ms


@contextmanager
def locked_package(root: Path, package_id: str):
    locks = root / "collections" / "locks"
    locks.mkdir(parents=True, exist_ok=True)
    path = locks / f"{package_id}.lock"
    path.touch(exist_ok=True); path.chmod(0o666)
    stream = path.open("a+")
    try:
        fcntl.flock(stream, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(stream, fcntl.LOCK_UN); stream.close()


def _facts(root: Path):
    return sorted((root / "collections" / "facts").glob("CL-*.json"))


def find_collection(root: Path, package_id: str) -> dict | None:
    mapping = root / "collections" / "by-package" / package_id
    if mapping.exists():
        path = root / "collections" / "facts" / f"{mapping.read_text().strip()}.json"
        if path.exists(): return json.loads(path.read_text())
    for path in _facts(root):
        value = json.loads(path.read_text())
        if value["package"]["package"] == package_id: return value
    return None


def materialize(root: Path, value: dict, fail_after: str | None = None) -> dict:
    package = value["package"]
    package_id = package["package"]
    collected = root / "collected" / f"{package_id}.json"
    if not collected.exists(): atomic_json(collected, package)
    interrupt(fail_after, "host_projection")
    mapping = root / "collections" / "by-package" / package_id
    if not mapping.exists(): atomic_text(mapping, value["collection"] + "\n")
    interrupt(fail_after, "association")
    (root / "inbox" / f"{package_id}.json").unlink(missing_ok=True)
    return value


def collect_package(ipc, package_id: str, collector: str, fail_after: str | None = None) -> dict:
    """Host-initiated transfer from Porter custody into recoverable Host custody."""
    root = Path(ipc)
    with locked_package(root, package_id):
        existing = find_collection(root, package_id)
        if existing is not None:
            materialize(root, existing, fail_after)
            return {**existing, "state": "ALREADY_COLLECTED"}
        acceptance_path = root / "acceptances" / f"{package_id}.json"
        if not acceptance_path.exists():
            raise ValueError(f"Package {package_id} has no canonical acceptance")
        acceptance = json.loads(acceptance_path.read_text())
        value = {
            "protocol": "PORTER/1",
            "kind": "COLLECTION",
            "collection": f"CL-{uuid.uuid4().hex}",
            "package": acceptance["package"],
            "acceptance": acceptance["acceptance"],
            "collector": collector,
            "collected_at_ms": now_ms(),
            "attests": "PACKAGE_RECOVERABLY_TRANSFERRED_TO_HOST_CUSTODY",
        }
        atomic_json(root / "collections" / "facts" / f"{value['collection']}.json", value)
        interrupt(fail_after, "collection")
        materialize(root, value, fail_after)
        return {**value, "state": "COLLECTED"}


def recover_collections(ipc) -> list[dict]:
    root = Path(ipc); recovered = []
    for path in _facts(root):
        value = json.loads(path.read_text())
        with locked_package(root, value["package"]["package"]): materialize(root, value)
        recovered.append(value)
    return recovered


def custody(ipc, package_id: str) -> dict:
    root = Path(ipc)
    acceptance = root / "acceptances" / f"{package_id}.json"
    collection = find_collection(root, package_id)
    if collection:
        return {"package": package_id, "current_custody": "RECIPIENT_HOST", "acceptance": collection["acceptance"], "collection": collection["collection"], "collector": collection["collector"]}
    if acceptance.exists():
        value = json.loads(acceptance.read_text())
        return {"package": package_id, "current_custody": "RECIPIENT_PORTER", "acceptance": value["acceptance"]}
    return {"package": package_id, "current_custody": "NOT_ACCEPTED_HERE"}
