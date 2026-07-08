"""Risk Engine — lightweight security scoring for sessions.

Computes a 0-100 risk score for each login based on signals like:
- Same browser / IP / device as previous session → lower risk
- New browser / country / VPN / multiple failed attempts → higher risk

The score is stored with the session and reported to the client.
It NEVER blocks logins. It is advisory only.
"""
from __future__ import annotations

import time
from typing import Callable

from saathi.security.store import SecurityStore, get_store


class RiskEngine:
    """Compute session risk scores based on deviation from known patterns."""

    # Signal weights
    SIGNALS = {
        "same_browser": -10,
        "same_ip": -10,
        "known_device": -20,
        "new_browser": 15,
        "new_country": 30,
        "vpn_proxy": 20,
        "failed_attempts_3plus": 25,
        "new_device": 15,
        "off_hours": 10,
    }

    def __init__(self, store: SecurityStore | None = None,
                 now: Callable[[], float] = time.time):
        self.store = store or get_store()
        self._now = now

    def score(self, user_id: str, *, browser: str = "", ip: str = "",
              device_name: str = "", country: str = "", timezone: str = "",
              failed_attempts: int = 0, hour: int | None = None) -> int:
        """Compute risk score (0-100) for a login attempt."""
        score = 0

        # Get previous sessions for comparison
        prev = self._previous_sessions(user_id, limit=5)

        if prev:
            last = prev[0]
            # Same browser?
            if browser and last.get("browser") == browser:
                score += self.SIGNALS["same_browser"]
            elif browser:
                score += self.SIGNALS["new_browser"]

            # Same IP?
            if ip and last.get("ip_address") == ip:
                score += self.SIGNALS["same_ip"]

            # Known device?
            known_devices = {s.get("device_name") for s in prev if s.get("device_name")}
            if device_name and device_name in known_devices:
                score += self.SIGNALS["known_device"]
            elif device_name:
                score += self.SIGNALS["new_device"]

        # Failed attempts
        if failed_attempts >= 3:
            score += self.SIGNALS["failed_attempts_3plus"]

        # Off-hours (assuming business hours 06:00-22:00 local)
        if hour is None:
            hour = time.localtime().tm_hour
        if hour < 6 or hour > 22:
            score += self.SIGNALS["off_hours"]

        # Clamp to 0-100
        return max(0, min(100, score))

    def label(self, score: int) -> tuple[str, str]:
        """Return (label, color) for a risk score."""
        if score <= 20:
            return ("Low", "green")
        if score <= 50:
            return ("Medium", "yellow")
        if score <= 75:
            return ("High", "orange")
        return ("Critical", "red")

    def _previous_sessions(self, user_id: str, limit: int = 5) -> list[dict]:
        """Get recent non-revoked sessions for comparison."""
        rows = self.store.db.execute(
            "SELECT browser, os, platform, device_name, ip_address, country,"
            " login_method, first_seen, last_seen, risk_score"
            " FROM sessions WHERE user_id=? AND revoked=0"
            " ORDER BY last_seen DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]
