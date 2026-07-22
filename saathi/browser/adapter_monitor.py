"""M17.26 — Browser adapter monitoring and privacy-safe alerts.

Integrates with session governance, Control Center read models, and alert delivery.
Alerts are deduplicated, free of secrets and raw screenshots.
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Optional


ALERT_KINDS = frozenset({
    "adapter_unavailable",
    "adapter_disconnected",
    "reconnect_failures",
    "session_stuck_active",
    "stale_lease",
    "page_identity_mismatch",
    "domain_policy_denial",
    "unexpected_redirect",
    "redaction_failure",
    "evidence_suppression_spike",
    "uncertain_external_effect",
    "reconciliation_overdue",
    "human_handoff_overdue",
    "raw_browser_attempt",
    "production_config_violation",
    "trading_guardian_denial",
    "browser_crash",
    "browser_process_orphaned",
})


@dataclass
class BrowserAlert:
    alert_id: str
    kind: str
    session_id: str = ""
    mission_id: str = ""
    mission_run_id: str = ""
    actor_id: str = ""
    message: str = ""
    error_category: str = ""
    created_at: float = 0.0
    dedupe_key: str = ""
    count: int = 1
    details: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "alert_id": self.alert_id,
            "kind": self.kind,
            "session_id": self.session_id,
            "mission_id": self.mission_id,
            "mission_run_id": self.mission_run_id,
            "actor_id": self.actor_id,
            "message": self.message,
            "error_category": self.error_category,
            "created_at": self.created_at,
            "dedupe_key": self.dedupe_key,
            "count": self.count,
            "details": dict(self.details),
            # privacy guarantees
            "screenshot_bytes": None,
            "secret_values": None,
        }


class BrowserAdapterMonitor:
    """In-process monitor for adapter/session health signals."""

    def __init__(self, *, dedupe_window_sec: float = 300.0):
        self.dedupe_window_sec = dedupe_window_sec
        self._alerts: list[BrowserAlert] = []
        self._dedupe: dict[str, BrowserAlert] = {}
        self._domain_denials: list[float] = []
        self._suppressions: list[float] = []

    def emit(
        self,
        kind: str,
        *,
        session_id: str = "",
        mission_id: str = "",
        mission_run_id: str = "",
        actor_id: str = "",
        message: str = "",
        error_category: str = "",
        details: dict | None = None,
    ) -> BrowserAlert:
        if kind not in ALERT_KINDS:
            kind = "adapter_unavailable"
        # Strip any accidental sensitive keys
        safe_details = {
            k: v for k, v in (details or {}).items()
            if k.lower() not in (
                "password", "token", "cookie", "screenshot", "secret",
                "storage_state", "authorization", "otp", "cvv",
            ) and not isinstance(v, (bytes, bytearray))
        }
        dedupe_raw = f"{kind}|{session_id}|{error_category}|{message[:80]}"
        dedupe_key = hashlib.sha256(dedupe_raw.encode()).hexdigest()[:16]
        now = time.time()
        prior = self._dedupe.get(dedupe_key)
        if prior and (now - prior.created_at) < self.dedupe_window_sec:
            prior.count += 1
            prior.created_at = now
            return prior
        alert = BrowserAlert(
            alert_id=f"balert-{dedupe_key}",
            kind=kind,
            session_id=session_id,
            mission_id=mission_id,
            mission_run_id=mission_run_id,
            actor_id=actor_id,
            message=message[:240],
            error_category=error_category,
            created_at=now,
            dedupe_key=dedupe_key,
            details=safe_details,
        )
        self._dedupe[dedupe_key] = alert
        self._alerts.append(alert)
        if kind == "domain_policy_denial":
            self._domain_denials.append(now)
        if kind == "redaction_failure":
            self._suppressions.append(now)
        # best-effort event fabric
        try:
            from saathi.events import bus
            bus.publish_sync("browser.adapter_alert", alert.as_dict())
        except Exception:
            pass
        return alert

    def record_domain_denial(self, **kwargs) -> BrowserAlert:
        return self.emit("domain_policy_denial", **kwargs)

    def record_disconnect(self, **kwargs) -> BrowserAlert:
        return self.emit("adapter_disconnected", **kwargs)

    def record_redaction_failure(self, **kwargs) -> BrowserAlert:
        return self.emit("redaction_failure", **kwargs)

    def record_uncertain(self, **kwargs) -> BrowserAlert:
        return self.emit("uncertain_external_effect", **kwargs)

    def record_trading_denial(self, **kwargs) -> BrowserAlert:
        return self.emit("trading_guardian_denial", **kwargs)

    def domain_denial_spike(self, *, window_sec: float = 60.0, threshold: int = 10) -> bool:
        now = time.time()
        recent = [t for t in self._domain_denials if now - t <= window_sec]
        self._domain_denials = recent
        return len(recent) >= threshold

    def recent_alerts(self, *, limit: int = 50) -> list[dict]:
        return [a.as_dict() for a in self._alerts[-limit:]]

    def control_center_snapshot(
        self,
        *,
        session: dict | None = None,
        health: dict | None = None,
        evidence: dict | None = None,
    ) -> dict:
        """Read model for Control Center — no secrets."""
        s = session or {}
        h = health or {}
        e = evidence or {}
        return {
            "session_status": s.get("status", ""),
            "adapter_status": h.get("state", ""),
            "active_domain": s.get("current_origin", ""),
            "allowed_scope": {
                "domains": s.get("allowed_domains", []),
                "action_classes": s.get("allowed_action_classes", []),
            },
            "current_action": s.get("metadata", {}).get("current_action", ""),
            "action_class": s.get("metadata", {}).get("action_class", ""),
            "approval_state": s.get("status") if "approval" in str(s.get("status", "")) else s.get("approval_scope", []),
            "human_handoff_state": s.get("human_handoff_state", ""),
            "reconciliation_state": s.get("reconciliation_status", ""),
            "evidence_classification": e.get("classification", ""),
            "screenshot_redaction_state": e.get("redaction_mode", ""),
            "last_error_category": h.get("last_error_category", ""),
            "lease_status": {
                "owner": s.get("lease_owner", ""),
                "expires_at": s.get("lease_expires_at", 0),
            },
            "expiry": s.get("expires_at", 0),
            "trading_guardian_engaged": bool(s.get("metadata", {}).get("trading_guardian")),
            # privacy
            "passwords": None,
            "otps": None,
            "cookies": None,
            "tokens": None,
            "full_private_page_content": None,
            "raw_storage_state": None,
            "sensitive_screenshots": None,
            "recent_alerts": self.recent_alerts(limit=10),
        }


_MON: BrowserAdapterMonitor | None = None


def default_browser_monitor() -> BrowserAdapterMonitor:
    global _MON
    if _MON is None:
        _MON = BrowserAdapterMonitor()
    return _MON


def reset_browser_monitor() -> None:
    global _MON
    _MON = None
