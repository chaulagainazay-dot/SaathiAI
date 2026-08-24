"""Lazy, path-keyed access to the legacy ``saathi.db`` stores.

Four modules used to open this database while being imported —
``saathi.selfimprove``, ``saathi.nepali``, ``saathi.tools.notes`` and
``saathi.tools.english`` — and ``Memory.__init__`` runs ``CREATE TABLE`` DDL, so
merely importing the server wrote into whatever database the path resolved to at
import time. Import happens before a test fixture or a validation harness can
set ``SAATHI_STATE_ROOT``, which is why an isolated backend still held four
read-write descriptors on the worktree's copy.

Everything here resolves the path at *first use* and caches by that resolved
path, so two configured roots can never share one connection or one ``Memory``.
Nothing is created by resolution alone; the store is built when a caller
actually needs it.
"""
from __future__ import annotations

import sqlite3
import threading

from .memory import Memory
from .runtime_paths import legacy_db_path

# Keyed by resolved path (and, for raw connections, the schema that owns them),
# so a change of root yields a different entry rather than a stale handle.
_lock = threading.RLock()
_memories: dict[str, Memory] = {}
_connections: dict[tuple[str, str], sqlite3.Connection] = {}


def legacy_memory() -> Memory:
    """The shared :class:`Memory` for the configured legacy database."""
    key = str(legacy_db_path())
    # Double-checked under one lock: concurrent first use must not build two
    # instances, each with its own connection, against the same file.
    with _lock:
        memory = _memories.get(key)
        if memory is None:
            memory = Memory(legacy_db_path())
            _memories[key] = memory
        return memory


def legacy_connection(schema: str, ddl: str, on_create=None) -> sqlite3.Connection:
    """A raw connection to the legacy database, with ``ddl`` applied once.

    ``schema`` names the caller's slice of the file (``"nepali"``,
    ``"selfimprove"``) so each keeps its own connection and applies its own
    ``CREATE TABLE IF NOT EXISTS`` statements exactly once per configured path.

    ``on_create`` runs once, immediately after the connection is built and the
    DDL applied — the place for seed rows. It fires per *connection*, so a
    caller never has to track whether it has already seeded a given database.
    """
    path = legacy_db_path()
    key = (str(path), schema)
    with _lock:
        conn = _connections.get(key)
        if conn is None:
            path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(path, check_same_thread=False)
            conn.executescript(ddl)
            if on_create is not None:
                on_create(conn)
            conn.commit()
            _connections[key] = conn
        return conn


def reset_legacy_stores() -> None:
    """Close and forget every cached store.

    Tests that move ``SAATHI_STATE_ROOT`` call this so the previous root's file
    descriptors are released rather than lingering for the rest of the session.
    """
    with _lock:
        for memory in _memories.values():
            try:
                memory.close()
            except Exception:
                pass
        for conn in _connections.values():
            try:
                conn.close()
            except Exception:
                pass
        _memories.clear()
        _connections.clear()
