"""M51 single-host SQLite-backed abuse controls for auth surfaces.

Fail-closed temporary lockouts. Not multi-host safe.
"""
from __future__ import annotations

import time
from typing import Callable


class AuthAbuseControls:
    """Deterministic attempt tracking with bounded lockout."""

    DEFAULTS = {
        "login": {"max": 8, "window_sec": 900, "lockout_sec": 900},
        "session_create": {"max": 20, "window_sec": 600, "lockout_sec": 600},
        "invite_accept": {"max": 10, "window_sec": 900, "lockout_sec": 900},
        "recovery": {"max": 5, "window_sec": 1800, "lockout_sec": 1800},
        "approval_action": {"max": 60, "window_sec": 600, "lockout_sec": 300},
    }

    def __init__(self, store, *, now: Callable[[], float] = time.time):
        self.store = store
        self._now = now

    def check(self, surface: str, key: str) -> tuple[bool, str]:
        """Return (allowed, reason)."""
        cfg = self.DEFAULTS.get(surface, self.DEFAULTS["login"])
        now = self._now()
        row = self.store.get_rate_limit(surface, key)
        if row and row.get("locked_until", 0) > now:
            return False, "temporarily_locked"
        return True, "ok"

    def record_failure(self, surface: str, key: str) -> dict:
        cfg = self.DEFAULTS.get(surface, self.DEFAULTS["login"])
        now = self._now()
        row = self.store.get_rate_limit(surface, key) or {
            "surface": surface,
            "key": key,
            "failures": 0,
            "window_start": now,
            "locked_until": 0.0,
        }
        if now - float(row.get("window_start") or 0) > cfg["window_sec"]:
            row["failures"] = 0
            row["window_start"] = now
            row["locked_until"] = 0.0
        row["failures"] = int(row.get("failures") or 0) + 1
        if row["failures"] >= cfg["max"]:
            row["locked_until"] = now + cfg["lockout_sec"]
            row["failures"] = 0
            row["window_start"] = now
        self.store.put_rate_limit(row)
        return row

    def record_success(self, surface: str, key: str) -> None:
        self.store.clear_rate_limit(surface, key)

    def owner_clear(self, surface: str, key: str) -> None:
        """Owner/admin recovery path — clear lockout."""
        self.store.clear_rate_limit(surface, key)
