"""M16 Control Center bounded aggregation.

A read/observation layer over the CANONICAL subsystems — it never executes,
never writes to subsystem stores, never calls providers. Each subsystem read is
wrapped so one failing source degrades to a typed `unavailable`/`degraded` cell
instead of failing the whole page. Every cell carries source + freshness so the
UI can show provenance and honesty (configured != healthy != live-tested).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


def _now() -> float:
    return time.time()


@dataclass
class Cell:
    """One aggregated value with provenance + honest failure state."""
    value: Any = None
    source: str = ""
    status: str = "ok"                # ok | degraded | unavailable
    observed_at: float = 0.0
    degraded_reason: str = ""

    def to_dict(self) -> dict:
        return {"value": self.value, "source": self.source, "status": self.status,
                "observed_at": self.observed_at, "degraded_reason": self.degraded_reason,
                "age_sec": round(_now() - self.observed_at, 2) if self.observed_at else None}


def guarded(source: str, fn: Callable[[], Any], *, timeout_note: str = "") -> Cell:
    """Run a subsystem read; never raise. Redact nothing here — sources are
    already secret-safe (health/metrics/gate); callers must not pass secrets."""
    started = _now()
    try:
        val = fn()
        return Cell(value=val, source=source, status="ok", observed_at=started)
    except Exception as e:  # partial failure → typed unavailable cell
        return Cell(value=None, source=source, status="unavailable",
                    observed_at=started, degraded_reason=str(e)[:200])


class ControlCenterAggregator:
    """Owner-scoped aggregation. `owner` is the authenticated user; every
    owner-scoped read is filtered by it (no cross-user data)."""

    def __init__(self, owner: str):
        self.owner = owner

    # ── individual subsystem cells (each guarded) ───────────────────────────
    def platform_health(self) -> Cell:
        from saathi.connectors.platform import health as H
        return guarded("connectors.health", lambda: H.platform_health())

    def connector_metrics(self) -> Cell:
        from saathi.connectors.platform import store as S
        return guarded("connectors.metrics",
                       lambda: S.default_store().metrics(owner=self.owner))

    def security_posture(self) -> Cell:
        from saathi.security.redteam.report import release_gate
        from saathi.security.redteam.baseline import load as load_baseline
        def _sec():
            gate = release_gate()
            base = load_baseline() or {}
            return {"verdict": gate["verdict"],
                    "release_blocking": gate["release_blocking"],
                    "confirmed_vulnerabilities": gate["confirmed_vulnerabilities"],
                    "baseline_totals": base.get("totals"),
                    "baseline_generated_at": base.get("generated_at")}
        return guarded("security.redteam", _sec)

    def pending_approvals(self) -> Cell:
        from saathi.connectors.platform import store as S
        return guarded("connectors.approvals",
                       lambda: S.default_store().pending_approvals(self.owner))

    def provider_matrix(self) -> Cell:
        from saathi.connectors.platform.enterprise import live_validation as LV
        return guarded("connectors.live_validation", lambda: LV.verification_matrix())

    def recent_events(self, limit: int = 25) -> Cell:
        from saathi.events.bus import default_bus
        def _ev():
            rows = default_bus().query(limit=limit)
            # sanitized already (event bus stores type/source/summary) — strip payloads
            return [{"type": r.get("type"), "source": r.get("source"),
                     "timestamp": r.get("timestamp"),
                     "summary": (r.get("payload") or {}).get("summary")
                     if isinstance(r.get("payload"), dict) else None}
                    for r in rows]
        return guarded("events.bus", _ev)

    def release_readiness(self) -> Cell:
        def _rel():
            from saathi.ops.release_gate import release_check
            code, report = release_check(run_secret_scan=False)
            gates = report.get("gates", {})
            return {"exit_code": code,
                    "storage_ok": (gates.get("storage") or {}).get("healthy"),
                    "config_ok": (gates.get("config") or {}).get("ok"),
                    "database_ok": (gates.get("database") or {}).get("all_ok"),
                    "backup_ok": (gates.get("backup_restore") or {}).get("backup_ok"),
                    "restore_verified": (gates.get("backup_restore") or {}).get("restore_verified")}
        return guarded("ops.release_gate", _rel)

    # ── composed read models ────────────────────────────────────────────────
    def overview(self) -> dict:
        health = self.platform_health()
        sec = self.security_posture()
        appr = self.pending_approvals()
        rel = self.release_readiness()
        metrics = self.connector_metrics()
        events = self.recent_events(limit=15)
        attention = self._attention(sec, appr, rel, health)
        return {
            "owner": self.owner,
            "generated_at": _now(),
            "platform_health": health.to_dict(),
            "security": sec.to_dict(),
            "pending_approvals": appr.to_dict(),
            "release_readiness": rel.to_dict(),
            "connector_metrics": metrics.to_dict(),
            "recent_timeline": events.to_dict(),
            "requires_attention": attention,
            "degraded_sources": [c.source for c in (health, sec, appr, rel, metrics, events)
                                 if c.status != "ok"],
        }

    def _attention(self, sec: Cell, appr: Cell, rel: Cell, health: Cell) -> list[dict]:
        """Rank what needs the user NOW. Real, actionable, honest."""
        items = []
        if sec.status == "ok" and sec.value:
            rb = sec.value.get("release_blocking", 0)
            if rb:
                items.append({"severity": "critical", "kind": "security",
                              "message": f"{rb} release-blocking security finding(s)",
                              "link": "/control/security"})
        if appr.status == "ok" and appr.value:
            n = len(appr.value)
            if n:
                items.append({"severity": "high", "kind": "approval",
                              "message": f"{n} approval(s) pending", "link": "/control/approvals"})
        if rel.status == "ok" and rel.value and rel.value.get("exit_code", 0) != 0:
            items.append({"severity": "high", "kind": "release",
                          "message": f"release gate failing (exit {rel.value['exit_code']})",
                          "link": "/control/release"})
        if health.status == "ok" and health.value:
            summary = health.value.get("summary", {})
            blocked = summary.get("environment-blocked", 0)
            if blocked:
                items.append({"severity": "info", "kind": "connector",
                              "message": f"{blocked} connector(s) environment-blocked (no credentials)",
                              "link": "/control/connectors"})
        # degraded sources are themselves attention items (honest)
        for c in (sec, appr, rel, health):
            if c.status != "ok":
                items.append({"severity": "medium", "kind": "observability",
                              "message": f"source {c.source} unavailable: {c.degraded_reason}",
                              "link": "/control/operations"})
        sev_order = {"critical": 0, "high": 1, "medium": 2, "info": 3}
        return sorted(items, key=lambda x: sev_order.get(x["severity"], 9))
