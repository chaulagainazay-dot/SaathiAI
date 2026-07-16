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


def _native_readiness() -> dict:
    """Fast native macOS readiness for the Computer Center (no actuation)."""
    try:
        from saathi.computer_agent import macos_permissions as P
        from saathi.computer_agent.macos_driver import available
        s = P.summary()
        return {"pyobjc": available().get("available", False),
                "accessibility_ready": s.get("native_accessibility_ready"),
                "screen_recording_ready": s.get("screen_recording_ready"),
                "actuation_ready": s.get("native_actuation_ready"),
                "note": "live reads (enumeration/identity/screenshot) verified; "
                        "actuation needs Accessibility + interactive session"}
    except Exception as e:
        return {"pyobjc": False, "error": str(e)[:120]}


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

    def computer_agent(self) -> Cell:
        """M17 Computer Center: registered computer connectors + honest provider
        availability (live desktop control env-blocked unless a provider is present)."""
        def _ca():
            from saathi.computer_agent.providers import provider_availability
            from saathi.connectors.platform import registry as R
            conns = [c.connector_id for c in R.all_connectors()
                     if c.category == "computer"]
            import os
            avail = provider_availability()
            importable = [k for k, v in avail.items()
                          if v.get("available") and k != "deterministic"]
            # a provider being importable is NOT proof of verified live control.
            # Live desktop control is only claimed when explicitly enabled AND a
            # provider is importable — otherwise honestly environment-blocked.
            live_enabled = os.getenv("SAATHI_COMPUTER_LIVE") == "1"
            live_desktop = "available" if (live_enabled and importable) else "environment_blocked"
            # fast permission readiness (no browser launch here)
            from saathi.computer_agent import permissions
            from saathi.computer_agent.browser_driver import browser_available
            perm = permissions.summary()
            return {"connectors": conns,
                    "tools": len([t for t in R.all_tools()
                                  if t.connector_id in conns]),
                    "providers": avail,
                    "importable_providers": importable,
                    "live_desktop_control": live_desktop,
                    "live_browser_ready": perm["live_browser_ready"],
                    "live_desktop_ready": perm["live_desktop_ready"],
                    "browser_binary": browser_available().get("path"),
                    "native_macos": _native_readiness(),
                    "permissions": perm["detail"],
                    "note": "live-browser workflow verified via CLI/live-report; desktop "
                            "permission-blocked (macOS TCC not granted)"}
        return guarded("computer_agent", _ca)

    def _placeholder_never_called(self):  # pragma: no cover
        pass

    def registry_health(self) -> Cell:
        """M17.21 Control Center Registry Health cell (read-only, safe summaries)."""
        def _rh():
            from saathi.application_harness import registry
            return registry.health()
        return guarded("application_harness.registry_health", _rh)

    def execution_gateway(self) -> Cell:
        """M17.22 ExecutionGateway metrics cell (running/queued/succeeded/failed…)."""
        def _eg():
            from saathi.execution.universal import default_boundary
            m = default_boundary().metrics()
            return {
                "running": m.get("running", 0),
                "queued": m.get("queued", 0),
                "succeeded": m.get("succeeded", 0),
                "failed": m.get("failed", 0),
                "denied": m.get("denied", 0),
                "approval_required": m.get("approval_required", 0),
                "average_runtime_sec": m.get("average_runtime_sec", 0),
                "retry_count": m.get("retry_count", 0),
                "recent_failures": m.get("recent_failures") or [],
                "by_status": m.get("by_status") or {},
            }
        return guarded("execution.gateway", _eg)

    def browser_execution(self) -> Cell:
        """M17.23 governed browser metrics (safe summaries only)."""
        def _be():
            from saathi.browser.governed import browser_metrics
            m = browser_metrics()
            return {
                "requested": m.get("requested", 0),
                "succeeded": m.get("succeeded", 0),
                "failed": m.get("failed", 0),
                "denied": m.get("denied", 0),
                "cancelled": m.get("cancelled", 0),
                "expired": m.get("expired", 0),
                "outcome_uncertain": m.get("outcome_uncertain", 0),
                "approval_required": m.get("approval_required", 0),
                "domain_denied": m.get("domain_denied", 0),
                "policy_denied": m.get("policy_denied", 0),
                "prompt_injection_detected": m.get("prompt_injection_detected", 0),
                "average_runtime_sec": m.get("average_runtime_sec", 0),
                "recent_failures": m.get("recent_failures") or [],
            }
        return guarded("browser.execution", _be)

    def mcp_health(self) -> Cell:
        """M18.1/M18.2 MCP governance + codebase memory index health."""
        def _mh():
            from saathi.mcp_governance.health import health_snapshot
            gov = health_snapshot()
            try:
                from saathi.codebase_memory.health import index_health
                idx = index_health().to_dict()
            except Exception as e:
                idx = {"status": "UNAVAILABLE", "degraded_reason": str(e)[:120]}
            return {
                "governance": gov,
                "index": idx,
                "status": idx.get("status") or gov.get("status"),
                "continuum_status": idx.get("continuum_status") or gov.get("continuum_status"),
                "mcp_id": gov.get("mcp_id") or idx.get("mcp_id"),
                "include_in_ceo_brief": bool(
                    gov.get("include_in_ceo_brief")
                    or (idx.get("status") in ("STALE", "CORRUPT", "UNAVAILABLE", "DEGRADED", "REBUILD_REQUIRED"))
                ),
            }
        return guarded("mcp.governance.health", _mh)

    def harnesses(self) -> Cell:
        """M17.3/M17.4 application-harness platform state (registry + discovery)
        plus the M17.9 durable run-ledger read model (active runs, heartbeats,
        recovery + attention items — owner-safe, never raw argv/output/secrets)."""
        def _h():
            from saathi.application_harness import registry, discovery
            s = registry.summary()
            d = discovery.discover()
            cell = {"total": s["total"], "by_trust": s["by_trust"],
                    "executable": s["executable"],
                    "available_apps": d.get("available_harnesses", []),
                    "dependency_blocked": d.get("dependency_blocked", []),
                    "harnesses": s["harnesses"],
                    "registry_health": registry.health()}
            try:
                from saathi.application_harness.run_ledger import default_ledger
                led = default_ledger()
                cell["run_ledger"] = led.read_model(self.owner)
                cell["ledger_health"] = {k: led.health()[k]
                                         for k in ("ok", "active", "by_state")}
                # M17.10 owner-safe stuck-run alerts (deduplicated)
                cell["run_alerts"] = led.open_alerts(self.owner)
                # M17.11 owner-safe notification delivery health + scheduler status
                cell["run_deliveries"] = led.open_deliveries(self.owner)
                cell["delivery_health"] = led.delivery_health()
                # M17.12 owner-safe multi-harness pipeline runs + health
                cell["pipelines"] = led.list_pipelines(self.owner, limit=25)
                cell["pipeline_health"] = led.pipeline_health(self.owner)
                # M17.13 owner-safe autonomous missions + health
                cell["missions"] = led.list_missions(self.owner, limit=25)
                cell["mission_health"] = led.mission_health(self.owner)
                # M17.15 owner-safe pipeline recovery (checkpoints + resume/retry)
                cell["pipeline_recoveries"] = led.list_recoveries(self.owner, limit=25)
                cell["recovery_health"] = led.recovery_health(self.owner)
                cell["invalid_checkpoints"] = [
                    c for c in led.checkpoints_owned(self.owner, limit=50)
                    if c["status"] != "valid"]
                # M17.16 owner-safe bounded parallel/branching graph pipelines
                cell["graph_pipelines"] = led.list_graphs(self.owner, limit=25)
                cell["graph_health"] = led.graph_health(self.owner)
                cell["graph_branches"] = [
                    b for b in led.branches_owned(self.owner, limit=50)
                    if b["state"] in ("failed", "approval_required", "stop_uncertain",
                                      "blocked")]
                # M17.14 owner-safe mission scheduling (schedules/occurrences/triggers)
                cell["schedules"] = led.list_schedules(self.owner, limit=25)
                cell["schedule_health"] = led.schedule_health(self.owner)
                cell["occurrences"] = led.list_occurrences(self.owner, limit=25)
                cell["occurrence_health"] = led.occurrence_health(self.owner)
                cell["triggers"] = led.list_triggers(self.owner, limit=25)
                cell["trigger_receipts"] = led.list_receipts(self.owner, limit=25)
                try:
                    from saathi.application_harness.run_scheduler import is_enabled, JOB_ID
                    cell["monitor_schedule"] = {"job": JOB_ID, "enabled": is_enabled()}
                except Exception:
                    cell["monitor_schedule"] = {"enabled": False}
            except Exception as e:            # degrade gracefully, never crash cell
                cell["run_ledger"] = {"unavailable": str(e)[:120]}
                cell["run_alerts"] = []
                cell["run_deliveries"] = []
                cell["pipelines"] = []
            return cell
        return guarded("application_harness", _h)

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

    def engineering_orchestrator(self) -> Cell:
        """M20.4 read-only Engineering Orchestrator facet (never executes)."""
        def _eng():
            from saathi.engineering.control_center_facet import (
                engineering_control_center_status,
            )
            return engineering_control_center_status()
        return guarded("engineering.orchestrator", _eng)

    def governed_inference(self) -> Cell:
        """M20.7 read-only governed inference facet (never generates)."""
        def _inf():
            from saathi.m20_console.status import inference_control_center_facet
            return inference_control_center_facet()
        return guarded("inference.governed", _inf)

    def m20_console(self) -> Cell:
        """M20.7 unified console rollup (read-only)."""
        def _m20():
            from saathi.m20_console.status import m20_console_status
            return m20_console_status()
        return guarded("m20.console", _m20)

    # ── composed read models ────────────────────────────────────────────────
    def overview(self) -> dict:
        health = self.platform_health()
        sec = self.security_posture()
        appr = self.pending_approvals()
        rel = self.release_readiness()
        metrics = self.connector_metrics()
        events = self.recent_events(limit=15)
        harn = self.harnesses()
        reg_h = self.registry_health()
        egw = self.execution_gateway()
        brw = self.browser_execution()
        mcp_h = self.mcp_health()
        eng = self.engineering_orchestrator()
        attention = self._attention(sec, appr, rel, health, harn, reg_h, egw, brw, mcp_h)
        # Engineering attention (quarantine / stall)
        if eng.status == "ok" and isinstance(eng.value, dict):
            ff = eng.value.get("facet_fields") or {}
            if ff.get("stall_status"):
                attention.append({
                    "severity": "medium", "kind": "engineering",
                    "message": "engineering session heartbeat stalled",
                    "link": "/control/engineering",
                })
            if (eng.value.get("lifecycle_state") == "quarantined"
                    or ff.get("final_session_status") == "quarantined"):
                attention.append({
                    "severity": "high", "kind": "engineering",
                    "message": "engineering session quarantined (integrity)",
                    "link": "/control/engineering",
                })
        return {
            "owner": self.owner,
            "generated_at": _now(),
            "platform_health": health.to_dict(),
            "security": sec.to_dict(),
            "pending_approvals": appr.to_dict(),
            "release_readiness": rel.to_dict(),
            "connector_metrics": metrics.to_dict(),
            "recent_timeline": events.to_dict(),
            "registry_health": reg_h.to_dict(),
            "execution_gateway": egw.to_dict(),
            "browser_execution": brw.to_dict(),
            "mcp_health": mcp_h.to_dict(),
            "engineering_orchestrator": eng.to_dict(),
            "requires_attention": attention,
            "degraded_sources": [c.source for c in (
                health, sec, appr, rel, metrics, events, reg_h, egw, brw, mcp_h, eng)
                                 if c.status != "ok"],
        }

    def _attention(self, sec: Cell, appr: Cell, rel: Cell, health: Cell,
                   harn: Cell | None = None,
                   reg_h: Cell | None = None,
                   egw: Cell | None = None,
                   brw: Cell | None = None,
                   mcp_h: Cell | None = None) -> list[dict]:
        """Rank what needs the user NOW. Real, actionable, honest."""
        items = []
        # M17.25 MCP memory degradation (operational attention only)
        if mcp_h is not None and mcp_h.status == "ok" and mcp_h.value:
            mv = mcp_h.value
            st = (mv.get("status") or "").lower()
            if st in ("degraded", "unavailable"):
                items.append({
                    "severity": "medium", "kind": "mcp_health",
                    "message": (
                        f"codebase-memory MCP {st}: "
                        f"{(mv.get('degraded_reason') or mv.get('last_error_category') or '')[:80]}"
                    ),
                    "link": "/control/mcp",
                })
        # M17.23 browser execution attention (failures / uncertain / policy)
        if brw is not None and brw.status == "ok" and brw.value:
            bv = brw.value
            if (bv.get("failed") or 0) > 0 or (bv.get("outcome_uncertain") or 0) > 0:
                items.append({
                    "severity": "high", "kind": "browser_execution",
                    "message": (
                        f"browser failed={bv.get('failed', 0)} "
                        f"uncertain={bv.get('outcome_uncertain', 0)}"
                    ),
                    "link": "/control/browser",
                })
            if (bv.get("approval_required") or 0) > 0:
                items.append({
                    "severity": "medium", "kind": "browser_approval",
                    "message": f"{bv.get('approval_required')} browser action(s) "
                               f"awaiting approval",
                    "link": "/control/browser",
                })
            if (bv.get("domain_denied") or 0) > 0 or (bv.get("policy_denied") or 0) > 0:
                items.append({
                    "severity": "medium", "kind": "browser_policy",
                    "message": (
                        f"browser policy denials "
                        f"domain={bv.get('domain_denied', 0)} "
                        f"policy={bv.get('policy_denied', 0)}"
                    ),
                    "link": "/control/browser",
                })
            if (bv.get("prompt_injection_detected") or 0) > 0:
                items.append({
                    "severity": "high", "kind": "browser_injection",
                    "message": f"prompt-injection markers detected in page content "
                               f"({bv.get('prompt_injection_detected')})",
                    "link": "/control/browser",
                })
        # M17.22 execution gateway (failures / approval backlog / high latency)
        if egw is not None and egw.status == "ok" and egw.value:
            ev = egw.value
            if (ev.get("failed") or 0) > 0:
                items.append({
                    "severity": "high", "kind": "execution_failed",
                    "message": f"{ev.get('failed')} execution(s) failed "
                               f"(retries={ev.get('retry_count', 0)})",
                    "link": "/control/execution",
                })
            if (ev.get("approval_required") or 0) > 0:
                items.append({
                    "severity": "medium", "kind": "execution_approval",
                    "message": f"{ev.get('approval_required')} execution(s) "
                               f"awaiting approval",
                    "link": "/control/execution",
                })
            if float(ev.get("average_runtime_sec") or 0) >= 30.0:
                items.append({
                    "severity": "medium", "kind": "execution_latency",
                    "message": f"avg execution runtime "
                               f"{ev.get('average_runtime_sec')}s",
                    "link": "/control/execution",
                })
        # M17.21 registry health alerts (dedupe by kind; no payload)
        if reg_h is not None and reg_h.status == "ok" and reg_h.value:
            rh = reg_h.value
            st = rh.get("overall_status")
            if st == "RED":
                items.append({
                    "severity": "critical", "kind": "registry_health",
                    "message": f"registry health RED (score {rh.get('health_score')})",
                    "link": "/control/registry",
                })
            elif st == "ORANGE":
                items.append({
                    "severity": "high", "kind": "registry_health",
                    "message": f"registry health ORANGE (score {rh.get('health_score')})",
                    "link": "/control/registry",
                })
            elif st == "YELLOW":
                items.append({
                    "severity": "medium", "kind": "registry_health",
                    "message": f"registry health YELLOW (score {rh.get('health_score')})",
                    "link": "/control/registry",
                })
            if rh.get("load_status") == "unsupported_schema":
                items.append({
                    "severity": "critical", "kind": "registry_schema",
                    "message": "registry schema mismatch / unsupported version",
                    "link": "/control/registry",
                })
            if rh.get("lock_state") == "held":
                items.append({
                    "severity": "medium", "kind": "registry_lock",
                    "message": "registry write lock currently held",
                    "link": "/control/registry",
                })
        # M17.10 harness stuck-run alerts (owner-safe; deduplicated in the ledger)
        if harn is not None and harn.status == "ok" and harn.value:
            for a in (harn.value.get("run_alerts") or []):
                items.append({"severity": a.get("severity", "medium"),
                              "kind": "harness_run",
                              "message": f"run {a['run_id']} {a['alert_class']}"
                                         + (f" ({a['status']})" if a.get("status") != "open" else ""),
                              "link": "/control/harnesses"})
            # M17.11 terminal notification-delivery failures need operator action
            for d in (harn.value.get("run_deliveries") or []):
                if d.get("status") == "terminal_failed":
                    items.append({"severity": "high", "kind": "harness_notification",
                                  "message": f"alert {d['alert_id']} delivery via "
                                             f"{d['channel']} terminally failed "
                                             f"({d.get('last_error_code', '')})",
                                  "link": "/control/harnesses"})
            # M17.12 failed multi-harness pipelines need owner attention
            for p in (harn.value.get("pipelines") or []):
                if p.get("state") == "failed":
                    items.append({"severity": "high", "kind": "harness_pipeline",
                                  "message": f"pipeline {p['pipeline_id']} "
                                             f"({p.get('name', '')}) failed at step "
                                             f"{p.get('failed_step')} "
                                             f"({p.get('failure_code', '')})",
                                  "link": "/control/harnesses"})
            # M17.13 autonomous missions needing owner action (failed / awaiting approval)
            for m in (harn.value.get("missions") or []):
                st = m.get("state")
                if st == "failed":
                    items.append({"severity": "high", "kind": "harness_mission",
                                  "message": f"mission {m['mission_id']} "
                                             f"({m.get('title', '')}) failed "
                                             f"({m.get('failure_code', '')})",
                                  "link": "/control/missions"})
                elif st == "approval_required":
                    items.append({"severity": "medium", "kind": "harness_mission",
                                  "message": f"mission {m['mission_id']} "
                                             f"({m.get('title', '')}) awaits approval",
                                  "link": "/control/missions"})
            # M17.15 pipeline-recovery attention (owner-safe summaries only)
            for r in (harn.value.get("pipeline_recoveries") or []):
                st = r.get("state")
                if st == "exhausted":
                    items.append({"severity": "high", "kind": "pipeline_recovery",
                                  "message": f"pipeline {r['pipeline_id']} retry exhausted "
                                             f"({r.get('failure_category', '')})",
                                  "link": "/control/recovery"})
                elif st == "stop_uncertain":
                    items.append({"severity": "high", "kind": "pipeline_recovery",
                                  "message": f"pipeline {r['pipeline_id']} STOP_UNCERTAIN "
                                             f"— manual review",
                                  "link": "/control/recovery"})
            for c in (harn.value.get("invalid_checkpoints") or []):
                sev = "high" if c["status"] == "missing_artifact" else "medium"
                items.append({"severity": sev, "kind": "pipeline_checkpoint",
                              "message": f"checkpoint {c['pipeline_id']} step "
                                         f"{c['step_index']} {c['status']} "
                                         f"({c.get('invalidation_reason', '')})",
                              "link": "/control/recovery"})
            # M17.16 graph-pipeline attention: failed / approval / stop_uncertain
            # branches and blocked joins (owner-safe summaries only)
            for g in (harn.value.get("graph_pipelines") or []):
                if g.get("state") == "failed":
                    items.append({"severity": "high", "kind": "graph_pipeline",
                                  "message": f"graph {g['pipeline_id']} "
                                             f"({g.get('name', '')}) failed — join "
                                             f"blocked ({g.get('failure_code', '')})",
                                  "link": "/control/graphs"})
            for b in (harn.value.get("graph_branches") or []):
                st = b.get("state")
                sev = "medium" if st == "approval_required" else "high"
                items.append({"severity": sev, "kind": "graph_branch",
                              "message": f"graph {b['pipeline_id']} branch "
                                         f"{b['branch_key']} {st} "
                                         f"({b.get('failure_code', '')})",
                              "link": "/control/graphs"})
            # M17.14 scheduler attention (owner-safe summaries only)
            for s in (harn.value.get("schedules") or []):
                if s.get("status") == "invalid":
                    items.append({"severity": "high", "kind": "mission_schedule",
                                  "message": f"schedule {s['schedule_id']} is invalid",
                                  "link": "/control/scheduler"})
            for o in (harn.value.get("occurrences") or []):
                st = o.get("state")
                if st == "failed":
                    items.append({"severity": "high", "kind": "mission_occurrence",
                                  "message": f"occurrence {o['occurrence_id']} failed "
                                             f"({o.get('failure_category', '')})",
                                  "link": "/control/scheduler"})
                elif st == "approval_required":
                    items.append({"severity": "medium", "kind": "mission_occurrence",
                                  "message": f"scheduled mission {o['occurrence_id']} "
                                             f"awaits approval",
                                  "link": "/control/scheduler"})
            occ_health = harn.value.get("occurrence_health") or {}
            if occ_health.get("stale_leases"):
                items.append({"severity": "medium", "kind": "mission_occurrence",
                              "message": f"{occ_health['stale_leases']} occurrence "
                                         f"lease(s) stale — reconcile pending",
                              "link": "/control/scheduler"})
            rejected = [r for r in (harn.value.get("trigger_receipts") or [])
                        if r.get("state") == "rejected"]
            if len(rejected) >= 5:
                items.append({"severity": "medium", "kind": "mission_trigger",
                              "message": f"{len(rejected)} event trigger rejection(s)",
                              "link": "/control/scheduler"})
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
