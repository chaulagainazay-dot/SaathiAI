"""Password Health — metrics and recommendations for password hygiene.

Computes:
- Strength score (0-4)
- Age (days since last change)
- Days until recommended rotation (90 days)
- History (previous passwords, count)

No fake data. If unavailable, returns Unknown.
"""
from __future__ import annotations

import time
from typing import Callable

from saathi.security.store import SecurityStore, get_store


RECOMMENDED_ROTATION_DAYS = 90


class PasswordHealth:
    """Compute password hygiene metrics from the security store."""

    def __init__(self, store: SecurityStore | None = None,
                 now: Callable[[], float] = time.time):
        self.store = store or get_store()
        self._now = now

    def metrics(self, user_id: str) -> dict:
        """Full password health report."""
        latest = self.store.latest_password(user_id)
        if not latest:
            return {
                "has_password": False,
                "strength": {"score": 0, "label": "Unknown", "checks": {}},
                "age_days": None,
                "last_changed": None,
                "days_until_rotation": None,
                "history_count": 0,
                "status": "unknown",
            }

        age_days = int((self._now() - latest["created_at"]) / 86400)
        days_until = max(0, RECOMMENDED_ROTATION_DAYS - age_days)
        history = self.store.password_history(user_id, limit=100)

        # Determine status
        if age_days > RECOMMENDED_ROTATION_DAYS:
            status = "overdue"
        elif age_days > RECOMMENDED_ROTATION_DAYS * 0.75:
            status = "soon"
        else:
            status = "good"

        # Re-compute strength for display
        from saathi import authsec
        # We don't have the plaintext, so we use the stored score
        score = latest.get("strength_score", 0)
        labels = ["Very weak", "Weak", "Fair", "Good", "Strong"]
        strength_label = labels[max(0, min(4, score))]

        return {
            "has_password": True,
            "strength": {
                "score": score,
                "label": strength_label,
                "checks": {},  # We don't store individual checks
            },
            "age_days": age_days,
            "last_changed": latest["created_at"],
            "days_until_rotation": days_until,
            "history_count": len(history),
            "status": status,
            "recommendation": self._recommendation(score, age_days, days_until),
        }

    def _recommendation(self, score: int, age_days: int, days_until: int) -> str:
        if score < 2:
            return "Your password is weak. Change it to a stronger one."
        if age_days > RECOMMENDED_ROTATION_DAYS:
            return f"Password is {age_days} days old. Recommended rotation was {days_until} days ago."
        if days_until <= 14:
            return f"Password rotation recommended in {days_until} days."
        return "Password health is good."

    def quick_status(self, user_id: str) -> str:
        """One-word status for dashboard display."""
        m = self.metrics(user_id)
        return m.get("status", "unknown")
