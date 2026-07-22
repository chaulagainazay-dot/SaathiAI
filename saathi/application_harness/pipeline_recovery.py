"""M17.15 governed pipeline recovery — resume, retry, checkpoint validation.

Lives IMMEDIATELY AROUND the existing PipelineRunner. It adds NO second pipeline
engine, execution engine, retry framework, verification path, or ledger: it decides
WHICH already-verified steps may be reused, reopens the failed pipeline, and hands
the remaining steps back to the SAME `PipelineRunner.execute_resume` (→
run_harness_action → adapter → independent verification → ledger).

Core guarantees (all deterministic; injectable clock; no real sleeps):
- reuse only a CONTIGUOUS prefix of independently-verified checkpoints that are
  still valid (owner + step + dependency fingerprints match, artifact exists inside
  the workspace and its integrity matches, verification passed, not invalidated);
- the FIRST non-reusable step and every step after it rerun through the governed
  service; no already-verified step reruns unless its checkpoint is invalid;
- retry is category-ALLOWLISTED (transient/infrastructure only) and bounded by the
  shared deterministic RETRY_SCHEDULE; approval/owner/param/verification/tamper
  failures never auto-retry;
- resume/retry NEVER imply approval — an approval-required step still stops closed;
- lease-based recovery claiming makes concurrent resume/retry requests resolve to
  one winner; crash reconciliation prefers reconciliation over duplicate execution.
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Optional

from saathi.application_harness import run_ledger as L
from saathi.application_harness.pipeline import (
    PipelineRunner, PipelineSpec, StepContext, default_resolver,
    step_fingerprint, dependency_fingerprint, file_fingerprint, _within,
)

# ONLY these failure categories are auto-retryable (transient / infrastructure).
# Anything not listed (approval, owner, verification, tamper, param, path escape,
# secret, manual-only, financial-execution, unknown/non-executable harness,
# cancellation, …) must NOT auto-retry.
RETRYABLE_CATEGORIES = {
    "timeout", "transient_lock", "sqlite_lock", "fs_contention", "adapter_timeout",
    "resource_unavailable", "interrupted", "transient",
    "PIPELINE_STEP_TIMEOUT", "HARNESS_TIMEOUT",
}


def is_retryable(category: str) -> bool:
    if not category:
        return False
    return category in RETRYABLE_CATEGORIES or category.lower() in RETRYABLE_CATEGORIES


def _validate_checkpoint(cp, step, plan, op, workspace, owner, dep_fp) -> tuple:
    """Return (ok: bool, reason: str, status_for_invalidation). Fail closed on ANY
    mismatch — owner, step identity, fingerprints, verification, artifact integrity,
    or workspace confinement."""
    if cp is None:
        return False, "no_checkpoint", L.CHECKPOINT_INVALID
    if cp["status"] != L.CHECKPOINT_VALID:
        return False, f"status:{cp['status']}", cp["status"]
    if cp["owner"] != owner:
        return False, "owner_mismatch", L.CHECKPOINT_INVALID
    if cp["step_name"] != step.name:
        return False, "step_identity", L.CHECKPOINT_INVALID
    if cp["step_fingerprint"] != step_fingerprint(step, plan, op, workspace):
        return False, "step_definition_changed", L.CHECKPOINT_INVALID
    if cp["dependency_fingerprint"] != dep_fp:
        return False, "dependency_changed", L.CHECKPOINT_INVALID
    if cp["verify_kind"] != (plan.verify_kind or ""):
        return False, "verification_policy_changed", L.CHECKPOINT_INVALID
    if not cp["verification_result"]:
        return False, "verification_failed", L.CHECKPOINT_VERIFICATION_FAILED
    if cp["artifact"]:
        path = os.path.join(workspace, cp["artifact"])
        if not _within(workspace, path) or not os.path.exists(path):
            return False, "missing_artifact", L.CHECKPOINT_MISSING_ARTIFACT
        if file_fingerprint(path) != cp["artifact_fingerprint"]:
            return False, "artifact_integrity", L.CHECKPOINT_MISSING_ARTIFACT
    return True, "", L.CHECKPOINT_VALID


class PipelineRecovery:
    """Coordinator around PipelineRunner. Never executes a tool itself."""

    def __init__(self, *, ledger: L.RunLedger | None = None,
                 runner: PipelineRunner | None = None, resolver=default_resolver,
                 lease_sec: float = 120.0):
        self.ledger = ledger or L.default_ledger()
        self.runner = runner or PipelineRunner(ledger=self.ledger, resolver=resolver)
        self.resolver = resolver
        self.lease_sec = lease_sec

    # ── longest contiguous valid verified prefix ───────────────────────────
    def reusable_prefix(self, spec: PipelineSpec, owner: str) -> dict:
        pid = spec.pipeline_id
        workspace = str(self.runner.runs_root / pid)
        artifacts: dict = {}
        artifact_fps: dict = {}
        prefix = 0
        stop_reason = ""
        for idx, step in enumerate(spec.steps):
            cp = self.ledger.get_checkpoint(pid, step_index=idx)
            try:
                plan = step.plan(StepContext(workspace=workspace,
                                             artifacts=dict(artifacts)))
            except Exception:
                stop_reason = "plan_error"; break
            defn, op = self.resolver(step.harness_id, step.operation_id)
            dep_fp = dependency_fingerprint(spec.steps[:idx], artifact_fps)
            ok, reason, bad_status = _validate_checkpoint(cp, step, plan, op,
                                                          workspace, owner, dep_fp)
            if not ok:
                if cp is not None and cp["status"] == L.CHECKPOINT_VALID:
                    # a previously-valid checkpoint that no longer holds → invalidate
                    self.ledger.invalidate_checkpoint(pid, step_index=idx,
                                                      reason=reason, status=bad_status)
                stop_reason = reason
                break
            prefix += 1
            if cp["artifact"]:
                artifacts[step.name] = os.path.join(workspace, cp["artifact"])
                artifact_fps[step.name] = cp["artifact_fingerprint"]
        return {"prefix": prefix, "artifacts": artifacts, "artifact_fps": artifact_fps,
                "stop_reason": stop_reason}

    # ── operator-explicit resume ───────────────────────────────────────────
    def resume(self, spec: PipelineSpec, *, owner: str, force_restart: bool = False,
               session_id: str = "resume", now=None, worker="recovery") -> dict:
        now = now if now is not None else L._now()
        pid = spec.pipeline_id
        if not pid:
            return {"ok": False, "reason": "no_pipeline_id"}
        run = self.ledger.inspect_pipeline(pid)
        if run is None:
            return {"ok": False, "reason": "unknown_pipeline"}
        if run["owner"] != owner:                       # owner check BEFORE anything
            return {"ok": False, "reason": "owner_mismatch"}
        if run["state"] != L.PIPELINE_FAILED:
            return {"ok": False, "reason": f"not_resumable:{run['state']}"}
        if self.ledger.get_recovery(pid) is None:
            self.ledger.upsert_recovery(pid, owner=owner,
                                        failure_category=run.get("failure_code", ""),
                                        attempt=1, now=now)
        # one resumer wins (concurrent resume requests → single resumed run)
        if not self.ledger.claim_recovery(pid, worker=worker, now=now,
                                          lease_sec=self.lease_sec):
            return {"ok": False, "reason": "recovery_claimed"}
        return self._continue(spec, owner, force_restart=force_restart,
                              session_id=session_id, now=now, is_retry=False)

    # ── policy retry (category-allowlisted, bounded, backed-off) ───────────
    def retry(self, spec: PipelineSpec, *, owner: str, session_id: str = "retry",
              now=None, worker="recovery") -> dict:
        now = now if now is not None else L._now()
        pid = spec.pipeline_id
        run = self.ledger.inspect_pipeline(pid)
        if run is None:
            return {"ok": False, "reason": "unknown_pipeline"}
        if run["owner"] != owner:
            return {"ok": False, "reason": "owner_mismatch"}
        rec = self.ledger.get_recovery(pid)
        if rec is None:
            return {"ok": False, "reason": "no_recovery_record"}
        if not is_retryable(rec["failure_category"]):
            return {"ok": False, "reason": "not_retryable",
                    "category": rec["failure_category"]}
        if rec["attempt"] >= rec["max_attempts"]:
            self.ledger.release_recovery(pid, state=L.RECOVERY_EXHAUSTED, now=now)
            return {"ok": False, "reason": "retry_exhausted"}
        if (rec["next_retry_at"] or 0) > now:
            return {"ok": False, "reason": "backoff_wait",
                    "next_retry_at": rec["next_retry_at"]}
        if run["state"] != L.PIPELINE_FAILED:
            return {"ok": False, "reason": f"not_resumable:{run['state']}"}
        if not self.ledger.claim_recovery(pid, worker=worker, now=now,
                                          lease_sec=self.lease_sec):
            return {"ok": False, "reason": "recovery_claimed"}
        return self._continue(spec, owner, force_restart=False, session_id=session_id,
                              now=now, is_retry=True)

    # ── shared continuation: reopen → reuse prefix → run remaining steps ───
    def _continue(self, spec, owner, *, force_restart, session_id, now, is_retry) -> dict:
        pid = spec.pipeline_id
        rec = self.ledger.get_recovery(pid) or {"attempt": 1, "max_attempts": 5}
        if force_restart:
            for idx in range(len(spec.steps)):
                self.ledger.invalidate_checkpoint(pid, step_index=idx,
                                                  reason="operator_full_restart")
            pref = {"prefix": 0, "artifacts": {}, "artifact_fps": {}, "stop_reason": "force_restart"}
        else:
            pref = self.reusable_prefix(spec, owner)
        reopened = self.ledger.reopen_pipeline(pid, now=now)
        if not reopened.get("ok"):
            self.ledger.release_recovery(pid, state=L.RECOVERY_RETRY_WAIT, now=now)
            return {"ok": False, "reason": reopened.get("reason")}
        res = self.runner.execute_resume(spec, owner, start_index=pref["prefix"],
                                         seed_artifacts=pref["artifacts"],
                                         seed_fps=pref["artifact_fps"],
                                         session_id=session_id)
        if res.get("ok"):
            self.ledger.release_recovery(pid, state=L.RECOVERY_RECOVERED,
                                         reused_steps=pref["prefix"],
                                         rerun_steps=res.get("rerun_steps", 0), now=now)
            return {"ok": True, "pipeline_id": pid, "state": L.PIPELINE_SUCCEEDED,
                    "reused_steps": pref["prefix"], "rerun_steps": res.get("rerun_steps", 0),
                    "resumed_from": pid, "stop_reason": pref["stop_reason"]}
        # rerun failed again
        code = res.get("failure_code", "")
        attempt = rec["attempt"] + 1
        if is_retry and is_retryable(code) and attempt < rec["max_attempts"]:
            self.ledger.release_recovery(pid, state=L.RECOVERY_RETRY_WAIT,
                                         attempt=attempt, retry_reason=code,
                                         next_retry_at=now + L.retry_delay(attempt),
                                         reused_steps=pref["prefix"],
                                         rerun_steps=res.get("rerun_steps", 0), now=now)
            state = L.RECOVERY_RETRY_WAIT
        elif is_retry and is_retryable(code):
            self.ledger.release_recovery(pid, state=L.RECOVERY_EXHAUSTED,
                                         attempt=attempt, retry_reason=code, now=now)
            state = L.RECOVERY_EXHAUSTED
        else:
            up = (code or "").upper()
            state = (L.RECOVERY_STOP_UNCERTAIN
                     if ("UNCERTAIN" in up or "VERIFICATION" in up) else L.RECOVERY_RETRY_WAIT)
            self.ledger.release_recovery(pid, state=state, retry_reason=code,
                                         reused_steps=pref["prefix"],
                                         rerun_steps=res.get("rerun_steps", 0), now=now)
        return {"ok": False, "pipeline_id": pid, "state": L.PIPELINE_FAILED,
                "failed_step": res.get("failed_step"), "failure_code": code,
                "recovery_state": state, "reused_steps": pref["prefix"],
                "rerun_steps": res.get("rerun_steps", 0)}

    # ── crash reconciliation (prefer reconcile over duplicate execution) ───
    def reconcile(self, *, now=None) -> dict:
        now = now if now is not None else L._now()
        settled = []
        for rec in self.ledger.reclaim_stale_recovery(now=now, lease_sec=self.lease_sec):
            pid = rec["pipeline_id"]
            run = self.ledger.inspect_pipeline(pid)
            if run and run["state"] == L.PIPELINE_SUCCEEDED:
                self.ledger.release_recovery(pid, state=L.RECOVERY_RECOVERED, now=now)
            else:
                # execution status uncertain → do NOT assume success; re-enable safely
                self.ledger.release_recovery(pid, state=L.RECOVERY_RETRY_WAIT, now=now)
            settled.append(pid)
        return {"reconciled": settled}

    def health(self, owner: str | None = None) -> dict:
        return self.ledger.recovery_health(owner)


_default: PipelineRecovery | None = None


def default_recovery() -> PipelineRecovery:
    global _default
    if _default is None:
        _default = PipelineRecovery()
    return _default
