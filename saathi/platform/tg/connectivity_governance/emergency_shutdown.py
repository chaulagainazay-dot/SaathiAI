"""M317 Emergency shutdown — dominates all authority."""
from __future__ import annotations

import time
from typing import Any

from saathi.platform.tg.connectivity_governance.models import AUTHORITY_VALUES


class EmergencyShutdown:
    def __init__(self):
        self._active = False
        self._record: dict[str, Any] | None = None
        self._history: list[dict[str, Any]] = []

    @property
    def active(self) -> bool:
        return self._active

    def status(self) -> dict[str, Any]:
        return {
            "ok": True,
            "active": self._active,
            "record": self._record,
            "overrides": {
                "approvals": True,
                "provider_eligibility": True,
                "credentials": True,
                "account_access": True,
                "execution_authority": True,
                "reconnection": True,
            },
            "recovery_requires_human_review": True,
            **AUTHORITY_VALUES,
        }

    def activate(self, *, actor: str, reason: str) -> dict[str, Any]:
        if not actor or actor.lower() in ("llm", "ai", "agent", "model"):
            return {"ok": False, "error": "HUMAN_ACTOR_REQUIRED", "message": "Emergency shutdown requires human actor"}
        if not reason:
            return {"ok": False, "error": "REASON_REQUIRED"}
        self._active = True
        self._record = {
            "actor": actor,
            "reason": reason,
            "activated_at": time.time(),
            "prevent_reconnection": True,
            "durable_evidence": True,
        }
        self._history.append(dict(self._record))
        return {
            "ok": True,
            "emergency_shutdown": True,
            "record": self._record,
            "dominates_all_authority": True,
            **AUTHORITY_VALUES,
        }

    def attempt_bypass(self) -> dict[str, Any]:
        """Any bypass attempt fails closed while shutdown is active."""
        return {
            "ok": False,
            "refused": True,
            "code": "EMERGENCY_SHUTDOWN_ACTIVE",
            "message": "Emergency shutdown cannot be bypassed",
            "active": self._active,
            **AUTHORITY_VALUES,
        }

    def recovery_request(self, *, actor: str, notes: str = "") -> dict[str, Any]:
        """Recovery is only a request — does not auto-clear without human review flag."""
        if not self._active:
            return {"ok": True, "message": "not_active", "active": False}
        return {
            "ok": True,
            "recovery_pending": True,
            "active": True,  # stays active until explicit human clear in future milestone
            "requires_human_review": True,
            "actor": actor,
            "notes": notes,
            "auto_cleared": False,
            **AUTHORITY_VALUES,
        }
