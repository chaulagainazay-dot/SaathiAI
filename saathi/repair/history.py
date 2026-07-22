"""Repair history store — JSON-backed, fingerprint-aware.

Records every incident outcome so recurring failures are recognized and the
same failed patch is not applied forever. After `max_attempts` unsuccessful
attempts for a fingerprint, the loop must escalate to MANUAL_REQUIRED.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from saathi.repair.secrets_scan import redact

ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_PATH = ROOT / "data" / "repair_history.json"


class RepairHistory:
    def __init__(self, path: str | os.PathLike | None = None):
        self.path = Path(path) if path else _DEFAULT_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write([])

    def _read(self) -> list[dict]:
        try:
            return json.loads(self.path.read_text() or "[]")
        except Exception:
            return []

    def _write(self, rows: list[dict]) -> None:
        self.path.write_text(json.dumps(rows, indent=1))

    def record(self, record: dict) -> dict:
        """Append a repair record. All string fields are secret-redacted."""
        safe = {k: (redact(v) if isinstance(v, str) else v)
                for k, v in record.items()}
        safe.setdefault("ts", time.time())
        rows = self._read()
        rows.append(safe)
        self._write(rows)
        return safe

    def attempts_for(self, fingerprint: str) -> int:
        """Count prior repair ATTEMPTS (repaired or failed) for a fingerprint."""
        return sum(1 for r in self._read()
                   if r.get("fingerprint") == fingerprint
                   and r.get("status") in ("repaired", "failed"))

    def last_status(self, fingerprint: str) -> str:
        rows = [r for r in self._read() if r.get("fingerprint") == fingerprint]
        return rows[-1].get("status", "") if rows else ""

    def all(self) -> list[dict]:
        return self._read()

    def get(self, incident_id: str) -> dict | None:
        for r in self._read():
            if r.get("incident_id") == incident_id:
                return r
        return None
