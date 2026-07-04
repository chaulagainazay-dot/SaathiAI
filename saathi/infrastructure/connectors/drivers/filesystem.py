"""Filesystem connector — files as a first-class connector.

Scripts, generated videos, PDFs, reports, screenshots, logs — every department
touches files. Routing them through the same contract gives uniform permissions,
diagnostics, and events. Optional `root` sandboxes all paths.
"""
from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path

from ..base import Connector, Health, Status, ConnectorError
from ..manifest import Manifest

_CAPS = frozenset({"read", "write", "watch", "move", "archive", "checksum", "list"})


class FilesystemConnector(Connector):
    id = "filesystem"

    def __init__(self, root: str | None = None):
        self._root = Path(root).resolve() if root else None

    def manifest(self) -> Manifest:
        return Manifest(
            id=self.id, display_name="Filesystem", category="storage", version=1,
            capabilities=_CAPS, permissions=frozenset({"read", "write"}),
            requires_auth=False, cost=0.0, latency="low", reliability=1.0,
            health_checks=frozenset({"root_writable"}))

    def authenticate(self) -> bool:
        return True

    def _resolve(self, path: str) -> Path:
        p = (self._root / path).resolve() if self._root else Path(path).resolve()
        if self._root and self._root not in p.parents and p != self._root:
            raise ConnectorError(f"path escapes sandbox root: {path!r}")
        return p

    def health(self) -> Health:
        try:
            base = self._root or Path.cwd()
            return Health(Status.OK if os.access(base, os.W_OK) else Status.DEGRADED,
                          f"root={base}")
        except Exception as e:
            return Health(Status.DOWN, str(e))

    def execute(self, capability: str, **payload):
        self._require(capability)
        if capability == "read":
            p = self._resolve(payload["path"])
            return p.read_bytes() if payload.get("binary") else p.read_text()
        if capability == "write":
            p = self._resolve(payload["path"])
            p.parent.mkdir(parents=True, exist_ok=True)
            data = payload["content"]
            p.write_bytes(data) if isinstance(data, (bytes, bytearray)) else p.write_text(data)
            return str(p)
        if capability == "checksum":
            p = self._resolve(payload["path"])
            return hashlib.sha256(p.read_bytes()).hexdigest()
        if capability == "watch":
            p = self._resolve(payload["path"])
            st = p.stat() if p.exists() else None
            return {"exists": st is not None,
                    "mtime": (st.st_mtime if st else None),
                    "size": (st.st_size if st else None)}
        if capability == "move":
            src, dest = self._resolve(payload["src"]), self._resolve(payload["dest"])
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dest))
            return str(dest)
        if capability == "archive":
            src = self._resolve(payload["path"])
            base = self._resolve(payload.get("dest", str(src) + ".zip")).with_suffix("")
            return shutil.make_archive(str(base), "zip", root_dir=str(src))
        if capability == "list":
            p = self._resolve(payload["path"])
            return sorted(str(x.relative_to(p)) for x in p.glob(payload.get("glob", "*")))
        raise ConnectorError(capability)  # unreachable
