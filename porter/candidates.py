from __future__ import annotations

import json
import os
import sqlite3
import uuid
from pathlib import Path


SCHEMA = "PORTER-CANDIDATES/1"


def _connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path, timeout=5)
    try:
        connection.execute("PRAGMA journal_mode=DELETE")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS metadata (name TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS candidates (package TEXT PRIMARY KEY, kind TEXT NOT NULL) WITHOUT ROWID"
        )
        connection.execute(
            "INSERT OR IGNORE INTO metadata(name,value) VALUES('schema',?)", (SCHEMA,)
        )
        return connection
    except Exception:
        connection.close()
        raise


def path_for(root: Path) -> Path:
    return root / "candidates" / "candidates.sqlite3"


def _prepare(root: Path) -> Path:
    folder = root / "candidates"
    folder.mkdir(parents=True, exist_ok=True)
    try:
        folder.chmod(0o777)
    except PermissionError:
        pass
    path = path_for(root)
    if path.exists():
        try:
            path.chmod(0o666)
        except PermissionError:
            pass
    return path


def publish(root: Path, package: dict) -> None:
    path = _prepare(root)
    connection = _connect(path)
    try:
        connection.execute(
            "INSERT OR REPLACE INTO candidates(package,kind) VALUES(?,?)",
            (package["package"], package["kind"]),
        )
        connection.commit()
    finally:
        connection.close()
    try:
        path.chmod(0o666)
    except PermissionError:
        pass


def settle(root: Path, package_id: str) -> None:
    path = _prepare(root)
    connection = _connect(path)
    try:
        connection.execute("DELETE FROM candidates WHERE package=?", (package_id,))
        connection.commit()
    finally:
        connection.close()
    try:
        path.chmod(0o666)
    except PermissionError:
        pass


def inspect(root: Path, kinds: set[str], limit: int) -> list[tuple[str, str]]:
    path = path_for(root)
    if not path.exists():
        rebuild(root)
    connection = None
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
        schema = connection.execute(
            "SELECT value FROM metadata WHERE name='schema'"
        ).fetchone()
        if schema != (SCHEMA,):
            connection.close()
            raise sqlite3.DatabaseError("unsupported candidate projection schema")
        if kinds:
            placeholders = ",".join("?" for _ in kinds)
            rows = connection.execute(
                f"SELECT package,kind FROM candidates WHERE kind IN ({placeholders}) ORDER BY package LIMIT ?",
                (*sorted(kinds), limit),
            ).fetchall()
        else:
            rows = connection.execute(
                "SELECT package,kind FROM candidates ORDER BY package LIMIT ?", (limit,)
            ).fetchall()
        connection.close()
        return [(str(package), str(kind)) for package, kind in rows]
    except sqlite3.DatabaseError:
        if connection is not None:
            connection.close()
        rebuild(root)
        return inspect(root, kinds, limit)


def canonical_candidates(root: Path) -> list[tuple[str, str]]:
    values = []
    collected = root / "collections" / "by-package"
    for path in sorted((root / "acceptances").glob("PKG-*.json")):
        value = json.loads(path.read_text())
        package = value["package"]
        if not (collected / package["package"]).exists():
            values.append((package["package"], package["kind"]))
    return values


def rebuild(root: Path) -> dict:
    target = _prepare(root)
    temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
    values = canonical_candidates(root)
    connection = _connect(temporary)
    try:
        connection.executemany(
            "INSERT INTO candidates(package,kind) VALUES(?,?)", values
        )
        connection.commit()
    finally:
        connection.close()
    temporary.chmod(0o666)
    os.replace(temporary, target)
    directory = os.open(target.parent, os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    return {"candidates": len(values), "bytes": target.stat().st_size}


def reconcile(root: Path) -> dict:
    expected = set(canonical_candidates(root))
    actual = set(inspect(root, set(), max(1, len(expected) + 1)))
    if actual != expected:
        result = rebuild(root)
        result.update({"repaired": True, "missing": len(expected - actual), "stale": len(actual - expected)})
        return result
    return {"candidates": len(actual), "bytes": path_for(root).stat().st_size, "repaired": False, "missing": 0, "stale": 0}
