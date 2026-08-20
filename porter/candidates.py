from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
import fcntl
import threading
import atexit
from contextlib import contextmanager
from pathlib import Path

from .history import enumerate_candidate_facts


SCHEMA = "PORTER-CANDIDATES/1"
FULL = "full"
RELAXED = "relaxed"
GROUPED = "grouped"
_connections: dict[str, tuple[sqlite3.Connection, tuple[int, int], str]] = {}
_read_connections: dict[str, tuple[sqlite3.Connection, tuple[int, int]]] = {}
_process_lock = threading.RLock()


def durability() -> str:
    value = os.getenv("PORTER_CANDIDATE_DURABILITY", GROUPED)
    if value not in {FULL, RELAXED, GROUPED}:
        raise ValueError(f"unsupported candidate durability strategy {value}")
    return value


def _connect(
    path: Path, initialize: bool = False, reconstruction: bool = False
) -> sqlite3.Connection:
    connection = sqlite3.connect(path, timeout=5, check_same_thread=False)
    try:
        strategy = durability()
        connection.execute(
            "PRAGMA synchronous=" + (
                "OFF" if reconstruction else
                "FULL" if strategy == FULL else
                "NORMAL" if strategy == GROUPED else
                "OFF"
            )
        )
        if reconstruction:
            # Rebuild is a single disposable construction followed by one atomic
            # publication. Keep it in one file so no unrenamed WAL can carry
            # part of the replacement state.
            connection.execute("PRAGMA journal_mode=DELETE")
        elif strategy == GROUPED:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                "PRAGMA wal_autocheckpoint=" + os.getenv("PORTER_CANDIDATE_CHECKPOINT_PAGES", "100")
            )
        if initialize:
            if strategy != GROUPED or reconstruction:
                connection.execute("PRAGMA journal_mode=DELETE")
            connection.execute(
                "CREATE TABLE metadata (name TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE candidates (package TEXT PRIMARY KEY, kind TEXT NOT NULL) WITHOUT ROWID"
            )
            connection.execute(
                "INSERT INTO metadata(name,value) VALUES('schema',?)", (SCHEMA,)
            )
        return connection
    except Exception:
        connection.close()
        raise


def path_for(root: Path) -> Path:
    return root / "candidates" / "candidates.sqlite3"


def close(root: Path | None = None) -> None:
    with _process_lock:
        keys = list(_connections) if root is None else [str(path_for(root))]
        for key in keys:
            retained = _connections.pop(key, None)
            if retained is not None:
                retained[0].close()
            reader = _read_connections.pop(key, None)
            if reader is not None:
                reader[0].close()


atexit.register(close)


def _existing_connection(path: Path) -> sqlite3.Connection:
    key = str(path)
    identity = (path.stat().st_dev, path.stat().st_ino)
    strategy = durability()
    retained = _connections.get(key)
    if retained is not None:
        connection, retained_identity, retained_strategy = retained
        if retained_identity == identity and retained_strategy == strategy:
            return connection
        connection.close()
    connection = _connect(path)
    _connections[key] = (connection, identity, strategy)
    return connection


def _read_connection(path: Path) -> sqlite3.Connection:
    key = str(path)
    identity = (path.stat().st_dev, path.stat().st_ino)
    retained = _read_connections.get(key)
    if retained is not None:
        connection, retained_identity = retained
        if retained_identity == identity:
            return connection
        connection.close()
    connection = sqlite3.connect(
        f"file:{path}?mode=ro", uri=True, timeout=5, check_same_thread=False
    )
    _read_connections[key] = (connection, identity)
    return connection


@contextmanager
def locked(root: Path):
    folder = root / "candidates"
    folder.mkdir(parents=True, exist_ok=True)
    lock = folder / ".projection.lock"
    lock.touch(exist_ok=True)
    try:
        lock.chmod(0o666)
    except PermissionError:
        pass
    with _process_lock:
        stream = lock.open("a+")
        try:
            fcntl.flock(stream, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)
            stream.close()


def invalidate(root: Path) -> None:
    path = path_for(root)
    close(root)
    for candidate in (path, path.with_name(path.name + "-journal"), path.with_name(path.name + "-wal"), path.with_name(path.name + "-shm")):
        candidate.unlink(missing_ok=True)


def _share_auxiliary_files(path: Path) -> None:
    for candidate in (
        path,
        path.with_name(path.name + "-journal"),
        path.with_name(path.name + "-wal"),
        path.with_name(path.name + "-shm"),
    ):
        if candidate.exists():
            try:
                candidate.chmod(0o666)
            except PermissionError:
                pass


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


def publish(root: Path, package: dict) -> bool:
    with locked(root):
        path = _prepare(root)
        if not path.exists():
            _rebuild_locked(root)
        try:
            connection = _existing_connection(path)
            try:
                connection.execute(
                    "INSERT OR REPLACE INTO candidates(package,kind) VALUES(?,?)",
                    (package["package"], package["kind"]),
                )
                connection.commit()
                _share_auxiliary_files(path)
            except Exception:
                connection.rollback()
                raise
        except (OSError, sqlite3.DatabaseError):
            # AC is already truth. A failed convenience update must leave an
            # unmistakably absent projection, never a valid-looking incomplete one.
            invalidate(root)
            return False
        try:
            path.chmod(0o666)
        except PermissionError:
            pass
        return True


def settle(root: Path, package_id: str) -> bool:
    with locked(root):
        path = _prepare(root)
        if not path.exists():
            _rebuild_locked(root)
        try:
            connection = _existing_connection(path)
            try:
                connection.execute("DELETE FROM candidates WHERE package=?", (package_id,))
                connection.commit()
                _share_auxiliary_files(path)
            except Exception:
                connection.rollback()
                raise
        except (OSError, sqlite3.DatabaseError):
            # Stale rows are safe, but an unreadable database is not useful.
            invalidate(root)
            return False
        try:
            path.chmod(0o666)
        except PermissionError:
            pass
        return True


def inspect(
    root: Path, kinds: set[str], limit: int, offset: int = 0
) -> list[tuple[str, str]]:
    path = path_for(root)
    if not path.exists():
        rebuild(root)
    try:
        connection = _read_connection(path)
        schema = connection.execute(
            "SELECT value FROM metadata WHERE name='schema'"
        ).fetchone()
        if schema != (SCHEMA,):
            raise sqlite3.DatabaseError("unsupported candidate projection schema")
        if kinds:
            placeholders = ",".join("?" for _ in kinds)
            rows = connection.execute(
                f"SELECT package,kind FROM candidates WHERE kind IN ({placeholders}) ORDER BY package LIMIT ? OFFSET ?",
                (*sorted(kinds), limit, offset),
            ).fetchall()
        else:
            rows = connection.execute(
                "SELECT package,kind FROM candidates ORDER BY package LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return [(str(package), str(kind)) for package, kind in rows]
    except sqlite3.DatabaseError:
        close(root)
        rebuild(root)
        return inspect(root, kinds, limit, offset)


def canonical_candidates(root: Path) -> list[tuple[str, str]]:
    return enumerate_candidate_facts(root)


def rebuild(root: Path) -> dict:
    with locked(root):
        return _rebuild_locked(root)


def _rebuild_locked(root: Path) -> dict:
    began = time.perf_counter_ns()
    target = _prepare(root)
    temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
    values = canonical_candidates(root)
    scanned = time.perf_counter_ns()
    connection = _connect(temporary, initialize=True, reconstruction=True)
    try:
        connection.executemany(
            "INSERT INTO candidates(package,kind) VALUES(?,?)", values
        )
        connection.commit()
    finally:
        connection.close()
    constructed = time.perf_counter_ns()
    temporary.chmod(0o666)
    close(root)
    for suffix in ("-journal", "-wal", "-shm"):
        target.with_name(target.name + suffix).unlink(missing_ok=True)
    os.replace(temporary, target)
    directory = os.open(target.parent, os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    published = time.perf_counter_ns()
    return {
        "candidates": len(values),
        "bytes": target.stat().st_size,
        "canonical_scan_ms": round((scanned - began) / 1e6, 3),
        "construction_ms": round((constructed - scanned) / 1e6, 3),
        "publication_ms": round((published - constructed) / 1e6, 3),
        "total_ms": round((published - began) / 1e6, 3),
    }


def reconcile(root: Path) -> dict:
    expected = set(canonical_candidates(root))
    actual = set(inspect(root, set(), max(1, len(expected) + 1)))
    if actual != expected:
        result = rebuild(root)
        result.update({"repaired": True, "missing": len(expected - actual), "stale": len(actual - expected)})
        return result
    return {"candidates": len(actual), "bytes": path_for(root).stat().st_size, "repaired": False, "missing": 0, "stale": 0}
