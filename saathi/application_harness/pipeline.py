"""M17.12 governed multi-harness pipeline — deterministic, sequential, fail-closed.

Composes N harness steps into one governed workflow. This is an ORCHESTRATOR, not
a second execution engine: every step is executed through the SAME governed
`service.run_harness_action` (ownership → trust → risk/approval → the sole
adapter → independent verification). The orchestrator only sequences steps, wires
each step's produced artifact into the next inside ONE confined workspace, and
records each step as a run in the durable M17.9 ledger plus a pipeline parent
record.

Guarantees (all live-validated):
- fail-closed short-circuit: the first step that is not `success`
  (blocked/failed/timeout/uncertain/approval_required) halts the pipeline; later
  steps NEVER run.
- workspace confinement: all step inputs/outputs stay inside a single per-pipeline
  workspace root; a produced/consumed/verify path that would escape is rejected
  BEFORE the step is executed (defence-in-depth over the adapter's own confine).
- owner-scoped, deterministic (no LLM in the orchestration decision), owner-safe
  records (never argv/output/secrets — only a workspace-relative artifact name).
- approval gates are honoured: a step whose operation needs approval halts the
  pipeline unless that step was explicitly pre-approved (no silent elevation).

Pipeline steps are declared in TRUSTED Python (like the pilots themselves) via a
`plan` callable that builds the step's argv from the confined workspace and the
prior artifacts. Parsing untrusted spec JSON, parallel/branching DAGs, retries and
scheduling are deliberately out of scope for this milestone.
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from saathi.application_harness import registry
from saathi.application_harness import service as _service
from saathi.application_harness.models import HarnessActionIntent
from saathi.application_harness.run_ledger import (
    RunLedger, default_ledger, PIPELINE_SUCCEEDED, PIPELINE_FAILED,
    RECOVERY_RETRY_WAIT,
)

# root under the (gitignored) harness data dir — every pipeline gets an isolated
# subdirectory that is the SOLE file root handed to every step.
_RUNS_ROOT = Path(__file__).resolve().parent.parent.parent / "data" / \
    "application_harness_runs" / "pipelines"

_SUCCESS = "success"


@dataclass(frozen=True)
class StepContext:
    """What a step's `plan` builder is given: the confined workspace absolute path
    and a name→absolute-path map of artifacts produced by prior steps."""
    workspace: str
    artifacts: dict


@dataclass(frozen=True)
class StepPlan:
    """The concrete, confined plan a step's builder returns."""
    argv: list
    produces: str = ""            # workspace-relative filename this step creates
    verify_kind: str = ""
    verify_target: str = ""       # absolute path (must be within the workspace)
    approved: bool = False        # explicit pre-approval for an approval-gated op


@dataclass(frozen=True)
class PipelineStep:
    name: str
    harness_id: str
    operation_id: str
    plan: Callable          # (StepContext) -> StepPlan  — trusted builder


@dataclass(frozen=True)
class PipelineSpec:
    name: str
    owner: str
    steps: list
    correlation_id: str = ""
    pipeline_id: str = field(default="")


def default_resolver(harness_id: str, operation_id: str):
    """Map (harness_id, operation_id) → (HarnessDefinition, HarnessOperation).
    Returns (None, None) for an unknown harness/operation → fail closed."""
    defn = registry.get(harness_id)
    ops = _pilot_operations().get(harness_id, {})
    return defn, ops.get(operation_id)


_OPS_CACHE: Optional[dict] = None


def _pilot_operations() -> dict:
    global _OPS_CACHE
    if _OPS_CACHE is None:
        from saathi.application_harness.pilots import (
            ffmpeg, sqlite_harness, jq_harness, zip_archive,
        )
        _OPS_CACHE = {}
        for mod in (ffmpeg, sqlite_harness, jq_harness, zip_archive):
            try:
                defn = mod.definition()
                _OPS_CACHE[defn.harness_id] = {o.operation_id: o
                                               for o in mod.operations()}
            except Exception:
                continue
    return _OPS_CACHE


def _within(root: str, path: str) -> bool:
    """True iff `path` resolves to a location inside `root` (symlink-safe)."""
    try:
        r = os.path.realpath(root)
        p = os.path.realpath(path)
        return p == r or p.startswith(r + os.sep)
    except Exception:
        return False


# ── M17.15 deterministic fingerprints (canonical; never hash raw secrets) ───
def _sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()[:24]


def file_fingerprint(path: str) -> str:
    """sha256 of an artifact's bytes; "" if missing (→ checkpoint not reusable)."""
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()[:24]
    except Exception:
        return ""


def step_fingerprint(step: "PipelineStep", plan: "StepPlan", op, workspace: str) -> str:
    """Deterministic fingerprint of a step's EXECUTION-AFFECTING definition:
    harness/operation identity, the workspace-normalized argv, produced artifact,
    verification policy, risk, and approval requirement. Cosmetic fields do not
    enter it; an execution-affecting change does. Stable across process restarts."""
    argv_norm = [a.replace(workspace, "<WS>") if isinstance(a, str) else a
                 for a in (plan.argv or [])]
    verify_norm = (plan.verify_target or "").replace(workspace, "<WS>")
    basis = json.dumps({
        "h": step.harness_id, "op": step.operation_id, "argv": argv_norm,
        "produces": plan.produces, "verify_kind": plan.verify_kind,
        "verify_target": verify_norm, "approved": bool(plan.approved),
        "risk": getattr(op, "risk", 0),
        "approval": getattr(op, "approval_requirement", "auto"),
    }, sort_keys=True, default=str)
    return _sha(basis)


def dependency_fingerprint(prior_steps, artifact_fps: dict) -> str:
    """Fingerprint of the upstream state a step depends on: the ordered prior step
    names and their produced-artifact fingerprints. A changed/missing upstream
    artifact changes this → downstream checkpoints fail closed."""
    basis = json.dumps([[s.name, artifact_fps.get(s.name, "")] for s in prior_steps],
                       sort_keys=True)
    return _sha(basis)


class PipelineRunner:
    """Runs a PipelineSpec. All steps share ONE confined workspace; the runner
    never bypasses the governed service."""

    def __init__(self, *, ledger: RunLedger | None = None, resolver=default_resolver,
                 runner=None, runs_root: str | None = None):
        self.ledger = ledger or default_ledger()
        self.resolver = resolver
        self.runner = runner or _service.run_harness_action
        self.runs_root = Path(runs_root) if runs_root else _RUNS_ROOT

    def run(self, spec: PipelineSpec, *, session_id: str = "pipeline") -> dict:
        owner = spec.owner
        if not owner:
            return {"ok": False, "reason": "empty_owner"}
        pid = spec.pipeline_id or ("pl_" + uuid.uuid4().hex[:16])
        workspace = str(self.runs_root / pid)
        os.makedirs(workspace, exist_ok=True)

        created = self.ledger.create_pipeline(
            pid, owner=owner, name=spec.name, step_count=len(spec.steps),
            correlation_id=spec.correlation_id)
        if not created.get("created"):
            return {"ok": False, "pipeline_id": pid, "reason": created.get("reason")}
        self.ledger.start_pipeline(pid)
        return self._execute(pid, spec, owner, workspace, session_id,
                             start_index=0, artifacts={}, artifact_fps={}, reused=0)

    def execute_resume(self, spec: PipelineSpec, owner: str, *, start_index: int,
                       seed_artifacts: dict, seed_fps: dict,
                       session_id: str = "resume") -> dict:
        """Continue an ALREADY-REOPENED pipeline_run from `start_index`, seeding the
        reused verified artifacts. The step loop is IDENTICAL to a fresh run — same
        governed run_harness_action, same confinement, same independent verification,
        same checkpoint writing. Reused steps are NOT re-executed."""
        pid = spec.pipeline_id
        workspace = str(self.runs_root / pid)
        return self._execute(pid, spec, owner, workspace, session_id,
                             start_index=start_index, artifacts=dict(seed_artifacts),
                             artifact_fps=dict(seed_fps), reused=start_index)

    def _execute(self, pid, spec, owner, workspace, session_id, *, start_index,
                 artifacts, artifact_fps, reused) -> dict:
        rerun = 0
        for idx in range(start_index, len(spec.steps)):
            step = spec.steps[idx]
            dep_fp = dependency_fingerprint(spec.steps[:idx], artifact_fps)
            outcome = self._run_step(pid, idx, step, owner, workspace, artifacts,
                                     session_id, dep_fp)
            if outcome["status"] != _SUCCESS:
                code = outcome.get("error_code") or outcome["status"]
                self.ledger.complete_pipeline(pid, state=PIPELINE_FAILED,
                                              failed_step=idx, failure_code=code)
                self._record_failure(pid, owner, code)
                return {"ok": False, "pipeline_id": pid, "state": PIPELINE_FAILED,
                        "failed_step": idx, "failed_step_name": step.name,
                        "failure_code": code, "steps_run": idx + 1,
                        "reused_steps": reused, "rerun_steps": rerun}
            rerun += 1
            if outcome.get("artifact"):
                artifacts[step.name] = os.path.join(workspace, outcome["artifact"])
                artifact_fps[step.name] = outcome.get("artifact_fp", "")
        self.ledger.complete_pipeline(pid, state=PIPELINE_SUCCEEDED)
        return {"ok": True, "pipeline_id": pid, "state": PIPELINE_SUCCEEDED,
                "steps_run": len(spec.steps), "reused_steps": reused,
                "rerun_steps": rerun, "artifacts": sorted(artifacts.keys())}

    def _record_failure(self, pid, owner, code) -> None:
        """Record a failed pipeline's recovery seed (owner-safe category) so a later
        governed retry/resume can find it. Never raises into the run path."""
        try:
            from saathi.application_harness.run_ledger import RECOVERY_STOP_UNCERTAIN
            rec = self.ledger.get_recovery(pid)
            up = code.upper()
            state = (RECOVERY_STOP_UNCERTAIN
                     if ("UNCERTAIN" in up or "VERIFICATION" in up) else RECOVERY_RETRY_WAIT)
            self.ledger.upsert_recovery(pid, owner=owner, failure_category=code,
                                        attempt=(rec["attempt"] if rec else 1),
                                        next_retry_at=0.0, state=state)
        except Exception:
            pass

    def _run_step(self, pid, idx, step, owner, workspace, artifacts, session_id,
                  dep_fp="") -> dict:
        defn, op = self.resolver(step.harness_id, step.operation_id)
        if defn is None or op is None:
            return self._record_blocked(pid, idx, step, run_id="",
                                        code="PIPELINE_UNKNOWN_HARNESS_OPERATION")
        if not defn.executable():
            return self._record_blocked(pid, idx, step, run_id="",
                                        code="PIPELINE_HARNESS_NOT_EXECUTABLE")

        # build the confined plan in trusted code
        try:
            plan = step.plan(StepContext(workspace=workspace, artifacts=dict(artifacts)))
        except Exception as e:                       # a builder blowing up is fail-closed
            return self._record_blocked(pid, idx, step, run_id="",
                                        code=f"PIPELINE_PLAN_ERROR:{type(e).__name__}")

        # defence-in-depth confinement: the produced file, the verify target, and
        # every prior artifact this step consumes must live inside the workspace.
        if plan.produces:
            if os.path.isabs(plan.produces) or ".." in Path(plan.produces).parts:
                return self._record_blocked(pid, idx, step, run_id="",
                                            code="PIPELINE_PATH_ESCAPE:produces")
            if not _within(workspace, os.path.join(workspace, plan.produces)):
                return self._record_blocked(pid, idx, step, run_id="",
                                            code="PIPELINE_PATH_ESCAPE:produces")
        if plan.verify_target and not _within(workspace, plan.verify_target):
            return self._record_blocked(pid, idx, step, run_id="",
                                        code="PIPELINE_PATH_ESCAPE:verify_target")

        # NOTE: a single harness action (run_harness_action) does not create a
        # process-journaled ledger `run` row — the pipeline_step record IS the
        # durable per-step ledger entry (same DB). `run_id` is a stable logical id.
        run_id = f"{pid}.s{idx}"
        intent = HarnessActionIntent(user_id=owner, session_id=session_id,
                                     harness_id=step.harness_id,
                                     operation_id=step.operation_id)
        res = self.runner(defn=defn, op=op, intent=intent, argv=plan.argv,
                          work_dir=workspace, file_roots=[workspace], owner=owner,
                          approved=plan.approved, verify_target=plan.verify_target,
                          verify_kind=plan.verify_kind)
        status = res.get("status", "failed")
        artifact = plan.produces if status == _SUCCESS else ""
        self.ledger.record_pipeline_step(
            pid, step_index=idx, step_name=step.name, harness_id=step.harness_id,
            operation_id=step.operation_id, run_id=run_id, status=status,
            error_code=res.get("error_code", ""), artifact=artifact)
        artifact_fp = ""
        if status == _SUCCESS:
            # a SUCCESS here is already independently verified by run_harness_action
            # (blocked/failed/uncertain/approval_required never reach this branch),
            # so this is exactly where a durable, reusable checkpoint belongs.
            artifact_fp = file_fingerprint(os.path.join(workspace, plan.produces)) \
                if plan.produces else ""
            self.ledger.upsert_checkpoint(
                "cp_" + uuid.uuid4().hex[:16], pipeline_id=pid, owner=owner,
                step_index=idx, step_name=step.name,
                step_fingerprint=step_fingerprint(step, plan, op, workspace),
                dependency_fingerprint=dep_fp, input_fingerprint=dep_fp,
                artifact=plan.produces, artifact_fingerprint=artifact_fp,
                verify_kind=plan.verify_kind, verification_result=True)
        return {"status": status, "error_code": res.get("error_code", ""),
                "artifact": artifact, "artifact_fp": artifact_fp}

    def _record_blocked(self, pid, idx, step, *, run_id, code) -> dict:
        self.ledger.record_pipeline_step(
            pid, step_index=idx, step_name=step.name, harness_id=step.harness_id,
            operation_id=step.operation_id, run_id=run_id, status="blocked",
            error_code=code)
        return {"status": "blocked", "error_code": code, "artifact": ""}


def run_pipeline(spec: PipelineSpec, **kw) -> dict:
    return PipelineRunner().run(spec, **kw)
