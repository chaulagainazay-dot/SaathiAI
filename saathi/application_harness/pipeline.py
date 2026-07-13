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

        artifacts: dict = {}
        for idx, step in enumerate(spec.steps):
            outcome = self._run_step(pid, idx, step, owner, workspace, artifacts,
                                     session_id)
            if outcome["status"] != _SUCCESS:
                self.ledger.complete_pipeline(
                    pid, state=PIPELINE_FAILED, failed_step=idx,
                    failure_code=outcome.get("error_code") or outcome["status"])
                return {"ok": False, "pipeline_id": pid, "state": PIPELINE_FAILED,
                        "failed_step": idx, "failed_step_name": step.name,
                        "failure_code": outcome.get("error_code") or outcome["status"],
                        "steps_run": idx + 1}
            if outcome.get("artifact"):
                artifacts[step.name] = os.path.join(workspace, outcome["artifact"])

        self.ledger.complete_pipeline(pid, state=PIPELINE_SUCCEEDED)
        return {"ok": True, "pipeline_id": pid, "state": PIPELINE_SUCCEEDED,
                "steps_run": len(spec.steps),
                "artifacts": sorted(artifacts.keys())}

    def _run_step(self, pid, idx, step, owner, workspace, artifacts, session_id) -> dict:
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
        return {"status": status, "error_code": res.get("error_code", ""),
                "artifact": artifact}

    def _record_blocked(self, pid, idx, step, *, run_id, code) -> dict:
        self.ledger.record_pipeline_step(
            pid, step_index=idx, step_name=step.name, harness_id=step.harness_id,
            operation_id=step.operation_id, run_id=run_id, status="blocked",
            error_code=code)
        return {"status": "blocked", "error_code": code, "artifact": ""}


def run_pipeline(spec: PipelineSpec, **kw) -> dict:
    return PipelineRunner().run(spec, **kw)
