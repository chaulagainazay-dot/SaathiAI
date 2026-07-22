"""Known-failure registry — tracks unresolved failures across runs.

Detects: known failure disappeared (resolved), signature changed, new failure
appeared, previously repaired failure returned (regressed). Complements
RepairHistory (which records repair *attempts*); this registry tracks failure
*state* over time.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
REGISTRY_PATH = ROOT / "data" / "known_failures.json"


def signature(node_id: str, exception_type: str = "", assertion: str = "") -> str:
    """Normalized failure fingerprint: node id + exception + assertion pattern."""
    basis = f"{node_id}|{exception_type}|{assertion.strip()[:120]}"
    return hashlib.sha1(basis.encode()).hexdigest()[:16]


class KnownFailures:
    def __init__(self, path: Path | None = None):
        self.path = path or REGISTRY_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("{}")

    def _read(self) -> dict:
        try:
            return json.loads(self.path.read_text() or "{}")
        except Exception:
            return {}

    def _write(self, data: dict) -> None:
        self.path.write_text(json.dumps(data, indent=1))

    def observe(self, failures: list[dict]) -> dict:
        """Reconcile current failures against the registry.

        `failures`: [{node_id, exception_type, assertion, subsystem, hypothesis}]
        Returns {"new": [...], "recurring": [...], "resolved": [...],
                 "returned": [...], "signature_changed": [...]}.
        """
        now = time.time()
        reg = self._read()
        seen_ids = set()
        report = {"new": [], "recurring": [], "resolved": [],
                  "returned": [], "signature_changed": []}

        for f in failures:
            node = f["node_id"]
            sig = signature(node, f.get("exception_type", ""), f.get("assertion", ""))
            seen_ids.add(node)
            entry = reg.get(node)
            if entry is None:
                reg[node] = {
                    "id": sig, "test_node_id": node,
                    "subsystem": f.get("subsystem", ""),
                    "first_seen": now, "last_seen": now,
                    "signature": sig,
                    "hypothesis": f.get("hypothesis", ""),
                    "status": "open", "owner": "auto-repair",
                    "attempts": 0, "blocked_reason": "", "report": "",
                }
                report["new"].append(node)
            else:
                entry["last_seen"] = now
                if entry.get("status") == "resolved":
                    entry["status"] = "returned"
                    report["returned"].append(node)
                elif entry.get("signature") != sig:
                    entry["signature"] = sig
                    report["signature_changed"].append(node)
                else:
                    report["recurring"].append(node)

        # anything open in the registry but absent now -> resolved
        for node, entry in reg.items():
            if node not in seen_ids and entry.get("status") in ("open", "returned"):
                entry["status"] = "resolved"
                entry["resolved_at"] = now
                report["resolved"].append(node)

        self._write(reg)
        return report

    def mark(self, node_id: str, *, status: str = "", attempts_delta: int = 0,
             blocked_reason: str = "", report_path: str = "") -> None:
        reg = self._read()
        entry = reg.get(node_id)
        if not entry:
            return
        if status:
            entry["status"] = status
        if attempts_delta:
            entry["attempts"] = entry.get("attempts", 0) + attempts_delta
        if blocked_reason:
            entry["blocked_reason"] = blocked_reason
        if report_path:
            entry["report"] = report_path
        self._write(reg)

    def open_failures(self) -> list[dict]:
        return [e for e in self._read().values()
                if e.get("status") in ("open", "returned")]

    def all(self) -> dict:
        return self._read()
