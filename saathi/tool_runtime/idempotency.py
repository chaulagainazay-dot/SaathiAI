"""M49.1 tool-call idempotency — in-process store (reuse-friendly; not a new ledger)."""
from __future__ import annotations

import hashlib
import json
import threading
import time
from typing import Any, Optional


def fingerprint(
    *,
    tool_id: str,
    tool_version: str,
    arguments: dict,
    authority: str,
    run_id: str,
    caller: str,
) -> str:
    payload = {
        "tool_id": tool_id,
        "tool_version": tool_version,
        "arguments": arguments,
        "authority": authority,
        "run_id": run_id,
        "caller": caller,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


class IdempotencyStore:
    """Process-local idempotency map. Keyed by (scope, key)."""

    def __init__(self):
        self._lock = threading.RLock()
        self._entries: dict[str, dict] = {}

    def _k(self, scope: str, key: str) -> str:
        return f"{scope}::{key}"

    def begin(self, scope: str, key: str, fp: str) -> dict:
        """Acquire ownership. Returns status dict."""
        with self._lock:
            full = self._k(scope, key)
            cur = self._entries.get(full)
            if cur is None:
                self._entries[full] = {
                    "status": "in_progress",
                    "fingerprint": fp,
                    "started_at": time.time(),
                    "result": None,
                }
                return {"status": "acquired", "fingerprint": fp}
            if cur["fingerprint"] != fp:
                return {
                    "status": "conflict",
                    "fingerprint": cur["fingerprint"],
                    "message": "same key different fingerprint",
                }
            if cur["status"] == "in_progress":
                return {"status": "in_progress", "fingerprint": fp}
            return {
                "status": "replay",
                "fingerprint": fp,
                "result": cur.get("result"),
            }

    def complete(self, scope: str, key: str, result: dict) -> None:
        with self._lock:
            full = self._k(scope, key)
            cur = self._entries.get(full)
            if not cur:
                return
            cur["status"] = "completed"
            cur["result"] = result
            cur["finished_at"] = time.time()

    def fail_release(self, scope: str, key: str) -> None:
        """Release in-progress on safe failure so retry can re-acquire."""
        with self._lock:
            full = self._k(scope, key)
            cur = self._entries.get(full)
            if cur and cur["status"] == "in_progress":
                del self._entries[full]


_DEFAULT = IdempotencyStore()


def default_idempotency_store() -> IdempotencyStore:
    return _DEFAULT
