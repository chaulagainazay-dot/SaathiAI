"""AutoRepairLoop — the orchestrator.

Pipeline: intake -> evidence -> classify -> policy -> rollback -> patch plan ->
patch apply -> focused tests -> full suite -> verify/regression guard ->
secret scan -> local commit -> history + report. Emits repair.* events.

Hard safety: never push/deploy; connector-auth + dependency issues are never
auto-patched as code; secret scan gates every commit; attempt limits stop
infinite loops; unrelated dirty work blocks auto-repair.
"""
from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from saathi.repair import evidence as ev_mod
from saathi.repair import policy as policy_mod
from saathi.repair import verify as verify_mod
from saathi.repair import rollback as rb_mod
from saathi.repair.classifier import classify
from saathi.repair.history import RepairHistory
from saathi.repair.incident import (
    RepairIncident, PolicyDecision, RepairStatus, FailureCategory, RepairLevel,
)
from saathi.repair.secrets_scan import scan_files
from saathi.repair.strategies import select_strategy, RepairStrategy

ROOT = Path(__file__).resolve().parent.parent.parent


@dataclass
class RepairLimits:
    max_attempts_per_incident: int = 2
    max_files_per_auto_repair: int = 8
    max_patch_lines: int = 400
    max_runtime_minutes: float = 20.0


@dataclass
class RepairOutcome:
    incident: RepairIncident
    status: RepairStatus
    message: str = ""
    regression: dict = field(default_factory=dict)
    events: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "incident_id": self.incident.incident_id,
            "status": self.status.value,
            "category": self.incident.category.value,
            "policy": self.incident.policy.value,
            "message": self.message,
            "repair_commit": self.incident.repair_commit,
            "rollback_ref": self.incident.rollback_ref,
            "regression": self.regression,
            "events": self.events,
        }


def _emit(name: str, payload: dict, sink: list[str]) -> None:
    sink.append(name)
    try:
        from saathi.events import bus
        bus.publish_sync(name, payload)
    except Exception:
        pass  # observability must never break the loop


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=str(ROOT),
                          capture_output=True, text=True, timeout=60)


class AutoRepairLoop:
    def __init__(self, history: RepairHistory | None = None,
                 limits: RepairLimits | None = None):
        self.history = history or RepairHistory()
        self.limits = limits or RepairLimits()

    # ---- Level 0: diagnose only -----------------------------------------
    def diagnose(self, inc: RepairIncident) -> RepairIncident:
        events: list[str] = []
        _emit("repair.incident.created", {"incident_id": inc.incident_id,
                                          "source": inc.source}, events)
        inc.evidence = ev_mod.collect(inc.evidence)
        _emit("repair.evidence.collected", {"incident_id": inc.incident_id}, events)
        classify(inc)
        _emit("repair.classified", {"incident_id": inc.incident_id,
                                    "category": inc.category.value,
                                    "confidence": inc.confidence}, events)
        prior = self.history.attempts_for(inc.fingerprint())
        inc.policy = policy_mod.decide(inc, prior_attempts=prior,
                                       max_attempts=self.limits.max_attempts_per_incident)
        _emit("repair.policy.decided", {"incident_id": inc.incident_id,
                                        "policy": inc.policy.value}, events)
        if inc.status == RepairStatus.OPEN:
            inc.status = RepairStatus.DIAGNOSED
        return inc

    # ---- Level 1: safe local repair -------------------------------------
    def run(self, inc: RepairIncident, *, approve: bool = False,
            strategies: list[RepairStrategy] | None = None) -> RepairOutcome:
        start = time.time()
        events: list[str] = []
        self.diagnose(inc)
        events += []  # diagnose emitted its own; keep a merged trace below

        fp = inc.fingerprint()
        prior = self.history.attempts_for(fp)
        if prior >= self.limits.max_attempts_per_incident:
            inc.status = RepairStatus.MANUAL_REQUIRED
            inc.notes = f"attempt limit reached ({prior}); escalating to manual"
            _emit("repair.manual_required", {"incident_id": inc.incident_id,
                                             "fingerprint": fp}, events)
            return self._finish(inc, RepairStatus.MANUAL_REQUIRED, inc.notes, events)

        if inc.policy == PolicyDecision.MANUAL_ONLY:
            msg = self._manual_guidance(inc)
            inc.status = RepairStatus.MANUAL_REQUIRED
            _emit("repair.manual_required", {"incident_id": inc.incident_id,
                                             "category": inc.category.value}, events)
            return self._finish(inc, RepairStatus.MANUAL_REQUIRED, msg, events)

        if inc.policy == PolicyDecision.APPROVAL_REQUIRED and not approve:
            inc.status = RepairStatus.DIAGNOSED
            return self._finish(inc, RepairStatus.DIAGNOSED,
                                "approval required before repair", events)

        if inc.policy == PolicyDecision.DIAGNOSE_ONLY:
            return self._finish(inc, RepairStatus.DIAGNOSED,
                                "diagnose-only; no safe strategy available", events)

        # AUTO_REPAIR_ALLOWED (or approved) -> need a concrete strategy
        strat = select_strategy(inc, strategies or [])
        if strat is None:
            inc.status = RepairStatus.DIAGNOSED
            return self._finish(inc, RepairStatus.DIAGNOSED,
                                "no concrete strategy parameters; manual root-cause needed",
                                events)
        inc.patch_plan = strat.plan(inc)

        # Rollback point (refuses if unrelated dirty work)
        allow = list(inc.patch_plan.files) + ["data/repair_history.json"]
        rp = rb_mod.create_rollback_point(inc.incident_id, allow_dirty=allow)
        if not rp.ok:
            inc.status = RepairStatus.FAILED
            return self._finish(inc, RepairStatus.FAILED, rp.refused_reason, events)
        inc.rollback_ref = rp.head
        _emit("repair.rollback.created", {"incident_id": inc.incident_id,
                                          "rollback": rp.head}, events)

        # Baseline: focused tests before
        focused = verify_mod.__dict__  # keep import used
        from saathi.repair.test_selector import focused_targets
        targets = focused_targets(inc)
        before = verify_mod.run_pytest(targets or ["tests/"])
        routes_before_ok, routes_before = verify_mod.server_smoke()

        # Apply patch
        _emit("repair.patch.started", {"incident_id": inc.incident_id,
                                       "strategy": strat.name}, events)
        try:
            changed = strat.apply(ROOT)
        except Exception as exc:
            rb_mod.rollback_to(rp.head)
            inc.status = RepairStatus.FAILED
            return self._finish(inc, RepairStatus.FAILED,
                                f"patch apply failed, rolled back: {exc!r}", events)

        if len(changed) > self.limits.max_files_per_auto_repair:
            rb_mod.rollback_to(rp.head)
            inc.status = RepairStatus.FAILED
            return self._finish(inc, RepairStatus.FAILED,
                                "patch touched too many files; rolled back", events)
        _emit("repair.patch.completed", {"incident_id": inc.incident_id,
                                         "files": changed}, events)

        # Verify ladder
        after_focused = verify_mod.run_pytest(targets or ["tests/"])
        _emit("repair.tests.focused.completed", after_focused.to_dict(), events)
        after_full = verify_mod.run_pytest(["tests/"])
        _emit("repair.tests.full.completed", after_full.to_dict(), events)
        routes_after_ok, routes_after = verify_mod.server_smoke()

        report = verify_mod.guard(before, after_full, routes_before, routes_after,
                                  focused_after=after_focused)

        if not report.success:
            rb_mod.rollback_to(rp.head)
            inc.status = RepairStatus.FAILED
            out = self._finish(inc, RepairStatus.FAILED,
                               "verification/regression failed; rolled back", events)
            out.regression = report.__dict__
            _emit("repair.failed", {"incident_id": inc.incident_id}, events)
            return out
        _emit("repair.verified", {"incident_id": inc.incident_id}, events)

        # Secret scan the staged/changed files BEFORE commit
        hits = scan_files([str(ROOT / f) for f in changed])
        if hits:
            rb_mod.rollback_to(rp.head)
            inc.status = RepairStatus.SECURITY_BLOCKED
            files = ", ".join(f"{Path(f).name}:{h.hits[0].line}" for f, h in hits.items())
            inc.category = FailureCategory.SECURITY_ERROR
            return self._finish(inc, RepairStatus.SECURITY_BLOCKED,
                                f"secret pattern detected in {files}; commit aborted", events)

        # Local commit (never push)
        commit = self._commit(inc, changed)
        inc.repair_commit = commit
        inc.status = RepairStatus.REPAIRED
        _emit("repair.committed", {"incident_id": inc.incident_id,
                                   "commit": commit}, events)
        out = self._finish(inc, RepairStatus.REPAIRED,
                           f"repaired and committed {commit}", events)
        out.regression = report.__dict__
        return out

    # ---------------------------------------------------------------------
    def _commit(self, inc: RepairIncident, files: list[str]) -> str:
        _git("add", *files)
        subsystem = inc.subsystem or inc.category.value.lower()
        msg = (f"repair({subsystem}): {inc.patch_plan.root_cause}\n\n"
               f"Incident: {inc.incident_id}\n"
               f"Category: {inc.category.value}\n"
               f"Strategy: {inc.patch_plan.strategy}\n"
               f"Rollback: {inc.rollback_ref}\n\n"
               "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>")
        _git("commit", "-q", "-m", msg)
        return _git("rev-parse", "HEAD").stdout.strip()[:12]

    def _manual_guidance(self, inc: RepairIncident) -> str:
        if inc.category == FailureCategory.CONNECTOR_AUTH_ERROR:
            return ("Connector is not connected or authenticated. This is a setup "
                    "action, not a code bug — reconnect/authorize the connector in "
                    "Account Center. Working code was NOT modified.")
        if inc.category == FailureCategory.DEPENDENCY_ERROR:
            return ("Dependency change required — needs explicit human approval "
                    "(major upgrades are Level 2). No code modified.")
        return "Manual action required; see diagnostic report."

    def _finish(self, inc: RepairIncident, status: RepairStatus, message: str,
                events: list[str]) -> RepairOutcome:
        self.history.record({
            "incident_id": inc.incident_id,
            "fingerprint": inc.fingerprint(),
            "category": inc.category.value,
            "root_cause": inc.patch_plan.root_cause if inc.patch_plan else "",
            "files_changed": inc.patch_plan.files if inc.patch_plan else [],
            "repair_commit": inc.repair_commit,
            "rollback_commit": inc.rollback_ref,
            "status": status.value,
            "confidence": inc.confidence,
            "notes": message,
        })
        return RepairOutcome(incident=inc, status=status, message=message,
                             events=events)
