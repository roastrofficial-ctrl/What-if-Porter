from __future__ import annotations

import fcntl
import json
import uuid
from contextlib import contextmanager
from pathlib import Path

from .lodgement import atomic_json, atomic_text, interrupt, now_ms
from .candidates import settle


@contextmanager
def locked_package(root: Path, package_id: str):
    locks = root / "collections" / "locks"
    locks.mkdir(parents=True, exist_ok=True)
    path = locks / f"{package_id}.lock"
    path.touch(exist_ok=True)
    try:
        path.chmod(0o666)
    except PermissionError:
        # Shared IPC volumes may retain a lock inode created by another local
        # process identity. Opening and flocking it is the concurrency
        # requirement; changing metadata on an already-accessible lock is not.
        pass
    stream = path.open("a+")
    try:
        fcntl.flock(stream, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(stream, fcntl.LOCK_UN)
        stream.close()


def _facts(root: Path):
    return sorted((root / "collections" / "facts").glob("CL-*.json"))


def find_collection(root: Path, package_id: str, scan_missing: bool = True) -> dict | None:
    mapping = root / "collections" / "by-package" / package_id
    if mapping.exists():
        path = root / "collections" / "facts" / f"{mapping.read_text().strip()}.json"
        if path.exists():
            return json.loads(path.read_text())
    if not scan_missing:
        return None
    for path in _facts(root):
        value = json.loads(path.read_text())
        if value["package"]["package"] == package_id:
            return value
    return None


def materialize(root: Path, value: dict, fail_after: str | None = None) -> dict:
    package = value["package"]
    package_id = package["package"]
    collected = root / "collected" / f"{package_id}.json"
    if not collected.exists():
        atomic_json(collected, package)
    interrupt(fail_after, "host_projection")
    mapping = root / "collections" / "by-package" / package_id
    if not mapping.exists() or mapping.read_text().strip() != value["collection"]:
        atomic_text(mapping, value["collection"] + "\n")
    interrupt(fail_after, "association")
    (root / "inbox" / f"{package_id}.json").unlink(missing_ok=True)
    settle(root, package_id)
    interrupt(fail_after, "candidate_removal")
    return value


def collect_package(
    ipc, package_id: str, collector: str, fail_after: str | None = None,
    scan_missing: bool = True,
) -> dict:
    """Host-initiated transfer from Porter custody into recoverable Host custody."""
    root = Path(ipc)
    with locked_package(root, package_id):
        existing = find_collection(root, package_id, scan_missing=scan_missing)
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
        # Publish the disposable direct association first.  It cannot make CL
        # true because readers still require the named canonical fact.  Once
        # CL crosses its unchanged atomic threshold, however, a missing mapping
        # can no longer force every subsequent new Collection to scan all CLs.
        atomic_text(
            root / "collections" / "by-package" / package_id,
            value["collection"] + "\n",
        )
        interrupt(fail_after, "association_reservation")
        atomic_json(
            root / "collections" / "facts" / f"{value['collection']}.json", value
        )
        interrupt(fail_after, "collection")
        materialize(root, value, fail_after)
        return {**value, "state": "COLLECTED"}


def recover_collections(ipc) -> list[dict]:
    root = Path(ipc)
    recovered = []
    for path in _facts(root):
        value = json.loads(path.read_text())
        with locked_package(root, value["package"]["package"]):
            materialize(root, value)
        recovered.append(value)
    return recovered


def _stat_signature(path: Path) -> list[int]:
    value = path.stat()
    return [value.st_size, value.st_mtime_ns]


def _frontier_record(root: Path, fact_path: Path, value: dict) -> dict:
    package_id = value["package"]["package"]
    return {
        "fact": _stat_signature(fact_path),
        "package": package_id,
        "collection": value["collection"],
        "collector": value["collector"],
        "package_kind": value["package"].get("kind"),
        "collected": _stat_signature(root / "collected" / f"{package_id}.json"),
        "association": _stat_signature(
            root / "collections" / "by-package" / package_id
        ),
    }


def _frontier_record_valid(root: Path, fact_path: Path, record: dict) -> bool:
    try:
        if record.get("fact") != _stat_signature(fact_path):
            return False
        package_id = record["package"]
        if record.get("collected") != _stat_signature(
            root / "collected" / f"{package_id}.json"
        ):
            return False
        association = root / "collections" / "by-package" / package_id
        if record.get("association") != _stat_signature(association):
            return False
        return association.read_text().strip() == record["collection"]
    except (KeyError, OSError, TypeError, ValueError):
        return False


def recover_collections_for_runtime(ipc) -> dict:
    """Audit disposable recovery progress, parsing only an exact extension.

    Canonical CL facts remain authoritative. Any malformed frontier, missing old
    fact, changed fact metadata, or changed required projection falls back to a
    complete canonical reconstruction.
    """
    root = Path(ipc)
    # Competing local Runtimes may recover simultaneously. Serialising the
    # disposable audit prevents a stale frontier writer from replacing a newer
    # exact extension; Package Collection locks remain the canonical boundary.
    with locked_package(root, "RECOVERY-FRONTIER"):
        return _recover_collections_for_runtime(root)


def _recover_collections_for_runtime(root: Path) -> dict:
    frontier_path = root / "collections" / "recovery" / "frontier.json"
    fact_paths = {path.name: path for path in _facts(root)}
    old_records = None
    try:
        frontier = json.loads(frontier_path.read_text())
        if frontier.get("schema") == "PORTER-COLLECTION-RECOVERY-FRONTIER/1":
            candidate = frontier.get("facts")
            if isinstance(candidate, dict):
                old_records = candidate
    except (OSError, json.JSONDecodeError, TypeError):
        pass

    valid = old_records is not None and set(old_records).issubset(fact_paths)
    if valid:
        valid = all(
            _frontier_record_valid(root, fact_paths[name], record)
            for name, record in old_records.items()
        )

    records = dict(old_records) if valid else {}
    names_to_parse = sorted(set(fact_paths) - set(records)) if valid else sorted(fact_paths)
    mode = "WARM_AUDIT" if valid and not names_to_parse else (
        "EXACT_EXTENSION" if valid else "FULL_RECONSTRUCTION"
    )
    for name in names_to_parse:
        path = fact_paths[name]
        value = json.loads(path.read_text())
        with locked_package(root, value["package"]["package"]):
            materialize(root, value)
        records[name] = _frontier_record(root, path, value)

    if not valid or names_to_parse:
        atomic_json(frontier_path, {
            "schema": "PORTER-COLLECTION-RECOVERY-FRONTIER/1",
            "facts": records,
        })

    collections = [
        {
            "collection": record["collection"],
            "collector": record["collector"],
            "package": {
                "package": record["package"],
                "kind": record.get("package_kind"),
            },
        }
        for _name, record in sorted(records.items())
    ]
    return {
        "mode": mode,
        "parsed_facts": len(names_to_parse),
        "audited_facts": len(records) - len(names_to_parse),
        "collections": collections,
    }


def custody(ipc, package_id: str) -> dict:
    root = Path(ipc)
    acceptance = root / "acceptances" / f"{package_id}.json"
    collection = find_collection(root, package_id)
    if collection:
        return {
            "package": package_id,
            "current_custody": "RECIPIENT_HOST",
            "acceptance": collection["acceptance"],
            "collection": collection["collection"],
            "collector": collection["collector"],
        }
    if acceptance.exists():
        value = json.loads(acceptance.read_text())
        return {
            "package": package_id,
            "current_custody": "RECIPIENT_PORTER",
            "acceptance": value["acceptance"],
        }
    return {"package": package_id, "current_custody": "NOT_ACCEPTED_HERE"}
