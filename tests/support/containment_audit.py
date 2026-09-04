"""A containment auditor that sees every shape a filesystem path can take.

The first version of this hook compared ``args[0]`` against ``str`` before
recording a ``sqlite3.connect``. Production code passes ``config.DB_PATH``, a
``pathlib.Path``, so every connection to the legacy database was dropped on the
floor and the ledger reported a clean run while ``lsof`` showed four read-write
descriptors on a database inside the git worktree. An auditor that silently
ignores the representation it is most likely to meet is worse than no auditor,
because it produces a confident wrong answer.

So: normalize through ``os.fspath``, accept ``str``/``bytes``/``os.PathLike``,
resolve relative paths and symlinks to the real target, understand SQLite's URI
form, and treat a writable target that cannot be classified as a violation
rather than as background noise.
"""
from __future__ import annotations

import os
import sys
import threading
from urllib.parse import unquote, urlparse

UNCLASSIFIED = "UNCLASSIFIED"

# Targets that name no file at all.
_NON_FILE = {":memory:", ""}

_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC
_WRITE_MODES = {"w", "a", "x", "+"}


def normalize_target(value) -> str | None:
    """Return the real absolute path ``value`` refers to, or ``None``.

    Accepts ``str``, ``bytes`` and any ``os.PathLike``. Relative paths resolve
    against the current directory; symlinks resolve to their target, because the
    containment question is about the file that actually gets written, not the
    name used to reach it.
    """
    if value is None:
        return None
    if isinstance(value, bytes):
        try:
            value = value.decode("utf-8")
        except UnicodeDecodeError:
            value = value.decode("utf-8", "replace")
    elif not isinstance(value, str):
        try:
            value = os.fspath(value)
        except TypeError:
            return None
        if isinstance(value, bytes):
            value = value.decode("utf-8", "replace")
    if not isinstance(value, str):
        return None

    value = value.strip()
    if value in _NON_FILE:
        return None
    return os.path.realpath(os.path.abspath(value))


def parse_sqlite_target(value) -> tuple[str | None, bool]:
    """Return ``(real_path, is_write)`` for a ``sqlite3.connect`` argument.

    SQLite's URI form carries the access mode, so a genuinely read-only
    attachment is recorded as a read. Everything else opens read-write.
    """
    raw = value
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", "replace")
    elif not isinstance(raw, (str, type(None))):
        try:
            raw = os.fspath(raw)
        except TypeError:
            return None, True
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", "replace")

    if isinstance(raw, str) and raw.startswith("file:"):
        parsed = urlparse(raw)
        path = unquote(parsed.path) or unquote(parsed.netloc)
        mode = ""
        for part in (parsed.query or "").split("&"):
            if part.startswith("mode="):
                mode = part[len("mode="):]
        return normalize_target(path), mode != "ro"

    return normalize_target(raw), True


def classify(path: str | None, zones: dict[str, str]) -> str:
    """Name the zone ``path`` falls in, longest prefix wins.

    An unrecognised path is ``UNCLASSIFIED`` — deliberately not "harmless".
    """
    if path is None:
        return UNCLASSIFIED
    best_name, best_len = UNCLASSIFIED, -1
    for name, root in zones.items():
        root = os.path.realpath(os.path.abspath(root))
        if path == root or path.startswith(root.rstrip(os.sep) + os.sep):
            if len(root) > best_len:
                best_name, best_len = name, len(root)
    return best_name


class ContainmentAudit:
    """Records what a process opens, and against which zone.

    ``zones`` maps a label to a directory root, e.g.
    ``{"isolated": root, "personal": "~/.saathi", "worktree": repo}``.
    """

    def __init__(self, zones: dict[str, str], allowed_write_zones: frozenset[str] | set[str] = ()):
        self.zones = dict(zones)
        self.allowed_write_zones = set(allowed_write_zones)
        self.records: list[dict] = []
        self._lock = threading.RLock()
        self._local = threading.local()

    # ── recording ───────────────────────────────────────────────────────────
    def record(self, event: str, target, write: bool) -> None:
        path = target if isinstance(target, str) or target is None else normalize_target(target)
        with self._lock:
            self.records.append({
                "event": event,
                "path": path,
                "write": bool(write),
                "zone": classify(path, self.zones),
            })

    def _hook(self, event, args):
        # The hook itself opens a file when a caller writes the ledger out;
        # re-entering here would recurse without bound.
        if getattr(self._local, "busy", False):
            return
        self._local.busy = True
        try:
            if event == "open":
                path, mode, flags = args[0], args[1], args[2]
                write = bool(set(mode or "") & _WRITE_MODES) if isinstance(mode, str) else False
                write = write or bool((flags or 0) & _WRITE_FLAGS)
                self.record("open", normalize_target(path), write)
            elif event == "sqlite3.connect":
                path, write = parse_sqlite_target(args[0])
                self.record("sqlite3.connect", path, write)
            elif event in ("os.remove", "os.rename", "os.mkdir"):
                self.record(event, normalize_target(args[0]), True)
        except Exception:
            pass
        finally:
            self._local.busy = False

    def install(self) -> "ContainmentAudit":
        sys.addaudithook(self._hook)
        return self

    # ── querying ────────────────────────────────────────────────────────────
    def writes(self) -> list[dict]:
        return [r for r in self.records if r["write"]]

    def write_paths(self, zone: str | None = None) -> list[str]:
        return sorted({
            r["path"] for r in self.writes()
            if r["path"] and (zone is None or r["zone"] == zone)
        })

    def reads_in(self, zone: str) -> list[str]:
        return sorted({
            r["path"] for r in self.records
            if not r["write"] and r["path"] and r["zone"] == zone
        })

    def violations(self) -> list[dict]:
        """Writable targets outside the allowed zones, unclassifiable included.

        Failing closed on ``UNCLASSIFIED`` is the point: a path the auditor does
        not recognise is the one most likely to be the escape.
        """
        return [r for r in self.writes() if r["zone"] not in self.allowed_write_zones]
