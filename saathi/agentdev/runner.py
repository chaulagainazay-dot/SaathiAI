"""M354 — Deterministic agent runner.

M351 ships one hard-coded mission narrative. This is the engine underneath: it
executes *any* mission plan by driving scripted handlers through one uniform
contract, and it records what happened while doing so.

Every step passes through seven phases, in order, with no way to skip one:

======== ==================================================================
receive  resolve the declared input artifacts; a missing input fails the step
process  the handler computes a payload — pure, no I/O, no clock, no random
produce  build the artifact, which runs the full M347 schema validation
record   persist it durably through :class:`ArtifactStore`
verify   read it back and compare a SHA-256 digest of the canonical form
handoff  name the next agent and the required next action
finish   stamp timing and mark the step complete
======== ==================================================================

**No prompts. No model. No reasoning.** A handler is a Python function of its
inputs. Given the same plan and the same inputs it produces byte-identical
artifact content — a property asserted by running the whole plan twice into two
stores and diffing everything but the timestamps.

Determinism has one deliberate seam: ``artifact_id``. M347 mints it from
``uuid4``, which would make two runs incomparable, so the runner assigns
``<kind4>_<mission>_<NN>`` from the step index instead. The seam is here, in one
function, rather than scattered through the handlers.

What the runner does *not* do: it never bypasses a gate. Gate steps call the
real :class:`GateEngine`, which refuses self-approval, missing evidence and
wrong-kind evidence exactly as it does for a human caller. A plan that tries to
skip a gate fails at the ``advance`` step, because the mission store checks the
exit gates on every hop.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from saathi.agentdev.artifacts import (
    Artifact,
    ArtifactKind,
    ArtifactStore,
    Claim,
    make_artifact,
    ArtifactError,
)
from saathi.agentdev.gates import GateEngine, GateError
from saathi.agentdev.missions import (
    DevMissionStore,
    Gate,
    MissionError,
    MissionState,
)
from saathi.agentdev.roles import require_role, RoleValidationError

RUNNER_VERSION = "agentdev.runner.v1"

#: The eight participants this milestone must support, mapped to the declared
#: role ids. The left column is the name in the specification; the right is the
#: ``agent_id`` in ``data/roles.json``. No new role is invented.
PARTICIPANTS: dict[str, str] = {
    "CEO": "ceo",
    "Manager": "program-manager",
    "Research": "research",
    "Architecture": "architecture",
    "Security": "security-governance",
    "Testing": "testing-verification",
    "Documentation": "documentation",
    "Code Review": "code-review",
}

PHASES = ("receive", "process", "produce", "record", "verify", "handoff", "finish")


class RunnerError(RuntimeError):
    def __init__(self, code: str, detail: str = ""):
        self.code = code
        self.detail = detail
        super().__init__(f"{code}" + (f" ({detail})" if detail else ""))


# --------------------------------------------------------------------------
# Plan
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class PlanStep:
    """One unit of work. Exactly one of three actions.

    ``agent``    a scripted participant produces one artifact
    ``gate``     the real gate engine evaluates and records a gate
    ``advance``  the mission moves to a declared state
    ``verdict``  the CEO records the terminal verdict, which only the CEO may do
    """

    step_id: str
    action: str  # agent | gate | advance | verdict
    agent_id: str = ""
    kind: str = ""
    title: str = ""
    task: str = ""
    inputs: tuple[str, ...] = ()          # step ids whose artifacts feed this one
    handoff_to: str = ""
    required_next_action: str = ""
    gate: str = ""
    approver: str = ""
    subject_author: str = ""
    evidence_from: tuple[str, ...] = ()   # step ids providing gate evidence
    target_state: str = ""
    actor: str = ""
    verdict: str = ""
    worktree: str = ""
    branch: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MissionPlan:
    dev_mission_id: str
    title: str
    objective: str
    starting_sha: str
    participants: tuple[str, ...]
    steps: tuple[PlanStep, ...]

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["steps"] = [s.to_dict() for s in self.steps]
        return d


# --------------------------------------------------------------------------
# Trace
# --------------------------------------------------------------------------


@dataclass
class PhaseResult:
    phase: str
    ok: bool
    detail: str = ""
    duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class StepTrace:
    step_id: str
    index: int
    action: str
    agent_id: str = ""
    phases: list[PhaseResult] = field(default_factory=list)
    input_artifact_ids: list[str] = field(default_factory=list)
    output_artifact_id: str = ""
    output_digest: str = ""
    handoff_to: str = ""
    status: str = "pending"  # pending | completed | failed
    failure_phase: str = ""
    failure_cause: str = ""
    failure_detail: str = ""
    duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["phases"] = [p.to_dict() for p in self.phases]
        return d


@dataclass
class ExecutionTrace:
    dev_mission_id: str
    runner: str = RUNNER_VERSION
    deterministic: bool = True
    model_used: str = ""
    steps: list[StepTrace] = field(default_factory=list)
    started_at: float = 0.0
    duration_ms: float = 0.0
    completed: bool = False
    final_state: str = ""
    terminal_verdict: str = ""

    @property
    def failed_steps(self) -> list[StepTrace]:
        return [s for s in self.steps if s.status == "failed"]

    def lineage(self) -> list[dict[str, Any]]:
        """Artifact-to-artifact edges, derived from the executed steps.

        Gate steps consume evidence without producing an artifact, so they
        contribute no edge — their record lives in the mission's gate history.
        """
        edges: list[dict[str, Any]] = []
        for step in self.steps:
            if not step.output_artifact_id:
                continue
            for source in step.input_artifact_ids:
                edges.append({
                    "from": source,
                    "to": step.output_artifact_id,
                    "via_step": step.step_id,
                })
        return edges

    def timing(self) -> dict[str, Any]:
        per_agent: dict[str, float] = {}
        per_phase: dict[str, float] = {}
        for step in self.steps:
            if step.agent_id:
                per_agent[step.agent_id] = round(
                    per_agent.get(step.agent_id, 0.0) + step.duration_ms, 3
                )
            for phase in step.phases:
                per_phase[phase.phase] = round(
                    per_phase.get(phase.phase, 0.0) + phase.duration_ms, 3
                )
        slowest = max(self.steps, key=lambda s: s.duration_ms, default=None)
        return {
            "total_ms": self.duration_ms,
            "per_agent_ms": dict(sorted(per_agent.items())),
            "per_phase_ms": dict(sorted(per_phase.items())),
            "slowest_step": slowest.step_id if slowest else None,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "runner": self.runner,
            "dev_mission_id": self.dev_mission_id,
            "deterministic": self.deterministic,
            "model_used": self.model_used or None,
            "completed": self.completed,
            "final_state": self.final_state,
            "terminal_verdict": self.terminal_verdict or None,
            "steps": [s.to_dict() for s in self.steps],
            "failures": [
                {
                    "step_id": s.step_id,
                    "phase": s.failure_phase,
                    "cause": s.failure_cause,
                    "detail": s.failure_detail,
                }
                for s in self.failed_steps
            ],
            "lineage": self.lineage(),
            "timing": self.timing(),
            "limitation": (
                "Scripted execution. Handlers are Python functions, so this "
                "establishes that the orchestration and gate path hold — not "
                "that a model would produce comparable output."
            ),
        }


# --------------------------------------------------------------------------
# Handlers
# --------------------------------------------------------------------------


@dataclass
class HandlerContext:
    """Everything a handler may read. Deliberately small and read-only."""

    plan: MissionPlan
    step: PlanStep
    inputs: tuple[Artifact, ...]

    def input_of_kind(self, kind: ArtifactKind) -> Artifact | None:
        for artifact in self.inputs:
            if artifact.kind == kind.value:
                return artifact
        return None


#: A handler returns the *body* of an artifact — never the envelope, which the
#: runner owns. Keeping the envelope out of handler reach is what stops a
#: handler forging an author, a mission or a SHA.
Handler = Callable[[HandlerContext], dict[str, Any]]

#: Fields the runner sets and a handler may not. A handler returning one is
#: refused by name rather than being silently dropped: a handler that tried to
#: name its own author is a fact the trace should carry.
ENVELOPE_FIELDS = frozenset({
    "artifact_id",
    "mission_id",
    "kind",
    "authoring_agent",
    "repository_sha",
    "title",
    "required_next_action",
    "status",
    "created_at",
    "updated_at",
})


def _claim(claim_id: str, statement: str, **kw: Any) -> Claim:
    return Claim(claim_id=claim_id, statement=statement, **kw)


def handle_ceo_intake(ctx: HandlerContext) -> dict[str, Any]:
    return {
        "body": ctx.step.task,
        "payload": {
            "sufficient_evidence_looks_like": [
                "a source-backed finding with its evidence reference",
                "a design naming what it reuses",
                "a security verdict covering authority and execution risk",
            ],
        },
    }


def handle_manager_assignment(ctx: HandlerContext) -> dict[str, Any]:
    return {
        "body": ctx.step.task,
        "payload": {
            "assignments": [
                {"agent_id": agent, "task": f"contribute to: {ctx.plan.objective}"}
                for agent in ctx.plan.participants
                if agent != "program-manager"
            ],
            "sequence": [s.step_id for s in ctx.plan.steps if s.action == "agent"],
        },
    }


def handle_research(ctx: HandlerContext) -> dict[str, Any]:
    return {
        "body": ctx.step.task,
        "claims": [
            _claim(
                "c1",
                "The agentdev package imports only saathi.safety and saathi.config.",
                kind="fact",
                evidence_ref="saathi/agentdev/__init__.py",
            ),
            _claim(
                "c2",
                "A new component therefore cannot silently depend on the product runtime.",
                kind="inference",
                rests_on=["c1"],
            ),
            _claim(
                "c3",
                "The host keeps one local model resident at a time.",
                kind="assumption",
                falsified_by="Two models resident together without swap pressure.",
            ),
        ],
        "payload": {
            "not_investigated": [
                "Behaviour of the package under concurrent writers.",
            ],
            "insufficient_evidence_on": [],
        },
        "limitations": ["Static reading only; nothing was executed."],
    }


def handle_architecture(ctx: HandlerContext) -> dict[str, Any]:
    findings = ctx.input_of_kind(ArtifactKind.RESEARCH_FINDINGS)
    return {
        "body": ctx.step.task,
        "claims": [
            _claim(
                "a1",
                "The design adds no second source of truth for authority.",
                kind="fact",
                evidence_ref="saathi/agentdev/roles.py",
            ),
        ],
        "payload": {
            "reuse_table": [
                {"need": "authority vocabulary", "reused": "saathi.safety.SafetyLevel"},
                {"need": "durable writes", "reused": "ArtifactStore atomic replace"},
            ],
            "new_components": [
                {
                    "name": "deterministic runner",
                    "why_no_existing_component": (
                        "No component executes a mission plan through a uniform "
                        "seven-phase contract with per-step traces."
                    ),
                }
            ],
            "rollback_path": "Delete the module; nothing else imports it.",
            "rests_on_findings": findings.artifact_id if findings else None,
        },
    }


def handle_security(ctx: HandlerContext) -> dict[str, Any]:
    return {
        "body": ctx.step.task,
        "claims": [
            _claim(
                "s1",
                "The runner exposes no shell, no credential and no network verb.",
                kind="fact",
                evidence_ref="saathi/agentdev/runner.py",
            ),
        ],
        "payload": {
            "verdict": "approved_with_conditions",
            "trading_guardian_impact": "none — no import path reaches trading",
            "global_config_impact": "none — no write outside the mission store",
            "conditions": [
                "A model-backed handler must not widen the handler contract.",
            ],
        },
    }


def handle_testing(ctx: HandlerContext) -> dict[str, Any]:
    return {
        "body": ctx.step.task,
        "payload": {
            "results": [
                {"command": "pytest tests/test_m354_agentdev_runner.py", "outcome": "pass"},
            ],
            "negative_paths": [
                {"case": "missing input artifact", "expected": "step fails at receive"},
                {"case": "self-approved gate", "expected": "gate engine refuses"},
                {"case": "gate skipped", "expected": "advance refuses"},
            ],
            "not_run": [
                "Any test requiring a provider — none is connected at this step.",
            ],
        },
    }


def handle_manager_handoff(ctx: HandlerContext) -> dict[str, Any]:
    """The fact-forcing step: a writable worktree needs importers and shapes named."""
    return {
        "body": ctx.step.task,
        "payload": {
            "scope": ["saathi/agentdev/runner.py"],
            "out_of_scope": [
                "saathi/engineering/", "saathi/missions/", "saathi/platform/",
            ],
            "importers": ["saathi/agentdev/cli.py"],
            "data_shapes": [
                {"name": "MissionPlan", "fields": ["dev_mission_id", "steps"]},
                {"name": "ExecutionTrace", "fields": ["steps", "timing", "lineage"]},
            ],
        },
    }


def handle_security_minutes(ctx: HandlerContext) -> dict[str, Any]:
    """Red-team minutes. Disagreement is recorded, never resolved by the chair."""
    return {
        "body": ctx.step.task,
        "payload": {
            "agreements": [
                "The seven-phase contract cannot be partially executed.",
            ],
            "disagreements": [],
            "outcome": "no_unresolved_objection",
            "attack_paths_considered": [
                "handler forging an artifact envelope",
                "gate step approving its own subject",
                "advance step skipping an exit gate",
            ],
        },
    }


def handle_code_review(ctx: HandlerContext) -> dict[str, Any]:
    return {
        "body": ctx.step.task,
        "payload": {
            "reviewed_author": ctx.step.subject_author or "backend-engineering",
            "findings": [],
            "verdict": "approved",
        },
    }


def handle_documentation(ctx: HandlerContext) -> dict[str, Any]:
    return {
        "body": ctx.step.task,
        "payload": {
            "documents": ["docs/ai-development/deterministic-runner.md"],
            "terminology_checked": True,
        },
    }


def handle_ceo_decision(ctx: HandlerContext) -> dict[str, Any]:
    return {
        "body": ctx.step.task,
        "payload": {
            "verdict": "APPROVED_WITH_LIMITATIONS",
            "unresolved_risks": [
                "Scripted handlers establish the orchestration path only.",
            ],
            "limitations": [
                "No model participated in this run.",
            ],
        },
    }


#: One handler per participant, keyed by the artifact kind it produces. A role
#: with two outputs (the CEO opens and closes a mission) has two entries.
HANDLERS: dict[tuple[str, str], Handler] = {
    ("ceo", ArtifactKind.MISSION_INTAKE.value): handle_ceo_intake,
    ("ceo", ArtifactKind.EXECUTIVE_DECISION.value): handle_ceo_decision,
    ("ceo", ArtifactKind.FINAL_SYNTHESIS.value): handle_ceo_decision,
    ("program-manager", ArtifactKind.TASK_ASSIGNMENT.value): handle_manager_assignment,
    ("program-manager", ArtifactKind.IMPLEMENTATION_HANDOFF.value): handle_manager_handoff,
    ("security-governance", ArtifactKind.MEETING_MINUTES.value): handle_security_minutes,
    ("research", ArtifactKind.RESEARCH_FINDINGS.value): handle_research,
    ("architecture", ArtifactKind.ARCHITECTURE_DECISION.value): handle_architecture,
    ("security-governance", ArtifactKind.SECURITY_REVIEW.value): handle_security,
    ("testing-verification", ArtifactKind.VERIFICATION_REPORT.value): handle_testing,
    ("code-review", ArtifactKind.CODE_REVIEW.value): handle_code_review,
    ("documentation", ArtifactKind.DOCUMENTATION_UPDATE.value): handle_documentation,
}


def resolve_handler(agent_id: str, kind: str) -> Handler:
    handler = HANDLERS.get((agent_id, kind))
    if handler is None:
        raise RunnerError("no_handler", f"{agent_id}:{kind}")
    return handler


# --------------------------------------------------------------------------
# Runner
# --------------------------------------------------------------------------


def deterministic_artifact_id(kind: str, mission_id: str, index: int) -> str:
    """Reproducible id. The one place run-to-run variability is removed."""
    return f"{kind[:4]}_{mission_id}_{index:02d}"


def artifact_digest(artifact: Artifact) -> str:
    """SHA-256 of the artifact's content, excluding its clocks."""
    payload = artifact.to_dict()
    payload.pop("created_at", None)
    payload.pop("updated_at", None)
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


class AgentRunner:
    """Executes a :class:`MissionPlan`. Writes only inside the mission store."""

    def __init__(self, root: Path | str, *, handlers: dict[tuple[str, str], Handler] | None = None):
        self.root = Path(root)
        self.artifacts = ArtifactStore(self.root)
        self.missions = DevMissionStore(self.root)
        self.gates = GateEngine(self.artifacts, self.missions)
        self.handlers = dict(HANDLERS if handlers is None else handlers)
        self._model_label = ""

    # ---- handler override, used by M356 ------------------------------------

    def override_handler(
        self, agent_id: str, kind: ArtifactKind | str, handler: Handler, *, model_label: str = ""
    ) -> None:
        """Replace one participant's handler.

        This is the seam M356 uses to put a local model behind exactly one
        agent. The replacement receives the same context and returns the same
        shape; it gains no new authority, and the artifact envelope stays with
        the runner.
        """
        value = kind.value if isinstance(kind, ArtifactKind) else str(kind)
        self.handlers[(agent_id, value)] = handler
        if model_label:
            self._model_label = model_label

    # ---- execution ----------------------------------------------------------

    def run(self, plan: MissionPlan, *, stop_on_failure: bool = True) -> ExecutionTrace:
        trace = ExecutionTrace(dev_mission_id=plan.dev_mission_id, started_at=time.time())
        trace.model_used = self._model_label
        overall = time.perf_counter()

        existing = self.missions.get(plan.dev_mission_id)
        if existing is None:
            self.missions.create(
                title=plan.title,
                objective=plan.objective,
                starting_sha=plan.starting_sha,
                participants=list(plan.participants),
                dev_mission_id=plan.dev_mission_id,
            )

        produced: dict[str, str] = {}  # step_id -> artifact_id
        for index, step in enumerate(plan.steps):
            step_trace = self._run_step(plan, step, index, produced)
            trace.steps.append(step_trace)
            if step_trace.status == "failed" and stop_on_failure:
                break

        mission = self.missions.get(plan.dev_mission_id)
        trace.final_state = mission.state if mission else ""
        trace.terminal_verdict = mission.terminal_verdict if mission else ""
        trace.duration_ms = round((time.perf_counter() - overall) * 1000, 3)
        trace.completed = not trace.failed_steps
        return trace

    # ---- one step -----------------------------------------------------------

    def _run_step(
        self, plan: MissionPlan, step: PlanStep, index: int, produced: dict[str, str]
    ) -> StepTrace:
        st = StepTrace(
            step_id=step.step_id, index=index, action=step.action, agent_id=step.agent_id
        )
        started = time.perf_counter()
        try:
            if step.action == "agent":
                self._run_agent_step(plan, step, index, produced, st)
            elif step.action == "gate":
                self._run_gate_step(plan, step, produced, st)
            elif step.action == "advance":
                self._run_advance_step(plan, step, st)
            elif step.action == "verdict":
                self._run_verdict_step(plan, step, st)
            else:
                raise RunnerError("unknown_action", step.action)
            st.status = "completed"
        except (
            RunnerError, ArtifactError, GateError, MissionError, RoleValidationError,
            TypeError, ValueError,
        ) as exc:
            # TypeError and ValueError are caught deliberately: a handler is
            # ordinary Python, and a buggy one should fail its own step with a
            # recorded cause rather than abort the whole run.
            st.status = "failed"
            st.failure_cause = getattr(exc, "code", type(exc).__name__)
            st.failure_detail = getattr(exc, "detail", str(exc))
            if not st.failure_phase:
                st.failure_phase = st.phases[-1].phase if st.phases else "receive"
        st.duration_ms = round((time.perf_counter() - started) * 1000, 3)
        return st

    def _phase(self, st: StepTrace, name: str):
        """Record one phase's outcome, including when it raises."""
        class _Phase:
            def __init__(self, trace: StepTrace, phase: str):
                self.trace, self.phase = trace, phase
                self.result = PhaseResult(phase=phase, ok=False)

            def __enter__(self):
                self.started = time.perf_counter()
                self.trace.phases.append(self.result)
                return self.result

            def __exit__(self, exc_type, exc, tb):
                self.result.duration_ms = round(
                    (time.perf_counter() - self.started) * 1000, 3
                )
                if exc_type is None:
                    self.result.ok = True
                else:
                    self.result.detail = str(exc)
                    self.trace.failure_phase = self.phase
                return False

        return _Phase(st, name)

    def _run_agent_step(
        self,
        plan: MissionPlan,
        step: PlanStep,
        index: int,
        produced: dict[str, str],
        st: StepTrace,
    ) -> None:
        # 1. receive
        with self._phase(st, "receive") as phase:
            role = require_role(step.agent_id)
            inputs: list[Artifact] = []
            for source in step.inputs:
                artifact_id = produced.get(source)
                if artifact_id is None:
                    raise RunnerError("input_step_not_executed", source)
                artifact = self.artifacts.get(plan.dev_mission_id, artifact_id)
                if artifact is None:
                    raise RunnerError("input_artifact_not_found", artifact_id)
                inputs.append(artifact)
            st.input_artifact_ids = [a.artifact_id for a in inputs]
            phase.detail = f"{len(inputs)} input(s) for {role.agent_id}"

        # 2. process — pure; no store, no clock, no filesystem
        with self._phase(st, "process") as phase:
            handler = self.handlers.get((step.agent_id, step.kind))
            if handler is None:
                raise RunnerError("no_handler", f"{step.agent_id}:{step.kind}")
            body = handler(HandlerContext(plan=plan, step=step, inputs=tuple(inputs)))
            if not isinstance(body, dict):
                raise RunnerError("handler_returned_non_mapping", step.agent_id)
            phase.detail = f"handler produced {sorted(body)}"

        # 3. produce — full M347 validation runs here
        with self._phase(st, "produce") as phase:
            forged = sorted(set(body) & ENVELOPE_FIELDS)
            if forged:
                raise RunnerError(
                    "handler_returned_envelope_field", ",".join(forged)
                )
            extra = dict(body)
            extra.setdefault("dependencies", st.input_artifact_ids)
            if step.worktree:
                extra.setdefault("worktree", step.worktree)
            if step.branch:
                extra.setdefault("branch", step.branch)
            artifact = make_artifact(
                mission_id=plan.dev_mission_id,
                kind=step.kind,
                authoring_agent=step.agent_id,
                repository_sha=plan.starting_sha,
                title=step.title,
                required_next_action=step.required_next_action or "next agent proceeds",
                artifact_id=deterministic_artifact_id(
                    step.kind, plan.dev_mission_id, index
                ),
                **extra,
            )
            phase.detail = artifact.artifact_id

        # 4. record
        with self._phase(st, "record") as phase:
            self.artifacts.put(artifact)
            phase.detail = f"persisted {artifact.artifact_id}"

        # 5. verify — read back and compare, so a silent write failure is caught
        with self._phase(st, "verify") as phase:
            stored = self.artifacts.get(plan.dev_mission_id, artifact.artifact_id)
            if stored is None:
                raise RunnerError("artifact_not_readable_after_write", artifact.artifact_id)
            if stored.kind != step.kind:
                raise RunnerError("kind_mismatch_after_write", stored.kind)
            digest = artifact_digest(stored)
            if digest != artifact_digest(artifact):
                raise RunnerError("digest_mismatch_after_write", artifact.artifact_id)
            st.output_digest = digest
            phase.detail = digest[:16]

        # 6. handoff
        with self._phase(st, "handoff") as phase:
            if step.handoff_to and step.handoff_to != "owner":
                require_role(step.handoff_to)
            st.handoff_to = step.handoff_to
            phase.detail = step.handoff_to or "terminal step"

        # 7. finish
        with self._phase(st, "finish") as phase:
            produced[step.step_id] = artifact.artifact_id
            st.output_artifact_id = artifact.artifact_id
            phase.detail = "recorded in the step index"

    def _run_gate_step(
        self, plan: MissionPlan, step: PlanStep, produced: dict[str, str], st: StepTrace
    ) -> None:
        with self._phase(st, "receive") as phase:
            evidence = []
            for source in step.evidence_from:
                artifact_id = produced.get(source)
                if artifact_id is None:
                    raise RunnerError("evidence_step_not_executed", source)
                evidence.append(artifact_id)
            st.input_artifact_ids = evidence
            phase.detail = f"{len(evidence)} evidence artifact(s)"

        with self._phase(st, "process") as phase:
            decision = self.gates.evaluate(
                plan.dev_mission_id,
                step.gate,
                approver=step.approver,
                subject_author=step.subject_author,
                evidence_artifact_ids=evidence,
            )
            phase.detail = "allowed" if decision.allowed else "; ".join(decision.refusals)

        with self._phase(st, "produce") as phase:
            if not decision.allowed:
                raise GateError("gate_refused", "; ".join(decision.refusals))
            phase.detail = step.gate

        with self._phase(st, "record") as phase:
            self.gates.pass_gate(
                plan.dev_mission_id,
                step.gate,
                approver=step.approver,
                subject_author=step.subject_author,
                evidence_artifact_ids=evidence,
            )
            phase.detail = f"gate {step.gate} recorded"

        with self._phase(st, "verify") as phase:
            mission = self.missions.require(plan.dev_mission_id)
            record = mission.gate(step.gate)
            if not record.passed:
                raise RunnerError("gate_not_recorded", step.gate)
            if record.approver == record.subject_author:
                raise RunnerError("self_approval_recorded", step.gate)
            phase.detail = f"{record.approver} approved {record.subject_author}"

        with self._phase(st, "handoff") as phase:
            st.handoff_to = step.handoff_to
            phase.detail = step.handoff_to or "lifecycle continues"

        with self._phase(st, "finish") as phase:
            phase.detail = "gate step complete"

    def _run_advance_step(self, plan: MissionPlan, step: PlanStep, st: StepTrace) -> None:
        with self._phase(st, "receive") as phase:
            mission = self.missions.require(plan.dev_mission_id)
            phase.detail = f"currently {mission.state}"

        with self._phase(st, "process") as phase:
            target = MissionState(step.target_state)
            phase.detail = f"{mission.state} -> {target.value}"

        with self._phase(st, "produce") as phase:
            phase.detail = "no artifact; a transition is not a document"

        with self._phase(st, "record") as phase:
            self.missions.advance(
                plan.dev_mission_id, target, actor=step.actor or "program-manager",
                reason=step.task,
            )
            phase.detail = f"advanced to {target.value}"

        with self._phase(st, "verify") as phase:
            after = self.missions.require(plan.dev_mission_id)
            if after.state != target.value:
                raise RunnerError("state_not_applied", after.state)
            phase.detail = after.state

        with self._phase(st, "handoff") as phase:
            st.handoff_to = step.handoff_to
            phase.detail = step.handoff_to or "lifecycle continues"

        with self._phase(st, "finish") as phase:
            phase.detail = "advance step complete"

    def _run_verdict_step(self, plan: MissionPlan, step: PlanStep, st: StepTrace) -> None:
        with self._phase(st, "receive") as phase:
            mission = self.missions.require(plan.dev_mission_id)
            phase.detail = f"{len(mission.gates)} gate record(s) on file"

        with self._phase(st, "process") as phase:
            phase.detail = f"proposed verdict {step.verdict}"

        with self._phase(st, "produce") as phase:
            phase.detail = "no artifact; the decision document was written earlier"

        with self._phase(st, "record") as phase:
            # ``set_terminal_verdict`` refuses any actor but the CEO, and refuses
            # a full approval while a veto or disagreement stands.
            self.missions.set_terminal_verdict(
                plan.dev_mission_id, step.verdict, actor=step.actor or "ceo"
            )
            phase.detail = step.verdict

        with self._phase(st, "verify") as phase:
            after = self.missions.require(plan.dev_mission_id)
            if after.terminal_verdict != step.verdict:
                raise RunnerError("verdict_not_applied", after.terminal_verdict)
            phase.detail = after.terminal_verdict

        with self._phase(st, "handoff") as phase:
            st.handoff_to = step.handoff_to
            phase.detail = step.handoff_to or "owner review"

        with self._phase(st, "finish") as phase:
            phase.detail = "verdict step complete"


# --------------------------------------------------------------------------
# The reference plan
# --------------------------------------------------------------------------

REFERENCE_SHA = "53b9b20736d5acf4a7ca3a9bd25b68d01e666a5d"
REFERENCE_MISSION = "dmrunner01"
#: Named, not created. The reference plan produces code-bound artifacts, which
#: must say which worktree and branch they describe; no worktree is made.
REFERENCE_WORKTREE = "reference-worktree"
REFERENCE_BRANCH = "agent/backend-engineering/dmrunner01-runner"


def reference_plan(
    dev_mission_id: str = REFERENCE_MISSION, sha: str = REFERENCE_SHA
) -> MissionPlan:
    """A plan exercising all eight participants and the full gate path."""
    return MissionPlan(
        dev_mission_id=dev_mission_id,
        title="Deterministic runner reference mission",
        objective=(
            "Execute one mission end to end with scripted participants, so the "
            "orchestration and gate path can be regression-tested without a model."
        ),
        starting_sha=sha,
        participants=tuple(sorted(PARTICIPANTS.values())),
        steps=(
            PlanStep(
                step_id="intake", action="agent", agent_id="ceo",
                kind=ArtifactKind.MISSION_INTAKE.value,
                title="Strategic objective", task="State the objective and its evidence bar.",
                handoff_to="program-manager",
                required_next_action="program manager decomposes the mission",
            ),
            PlanStep(
                step_id="decompose", action="advance", target_state="decomposed",
                actor="program-manager", task="Objective accepted for decomposition.",
                handoff_to="program-manager",
            ),
            PlanStep(
                step_id="assign", action="agent", agent_id="program-manager",
                kind=ArtifactKind.TASK_ASSIGNMENT.value,
                title="Task assignment", task="Assign each participant one task.",
                inputs=("intake",), handoff_to="research",
                required_next_action="research investigates",
            ),
            PlanStep(
                step_id="to_research", action="advance", target_state="research",
                actor="program-manager", task="Assignments issued.",
            ),
            PlanStep(
                step_id="research", action="agent", agent_id="research",
                kind=ArtifactKind.RESEARCH_FINDINGS.value,
                title="Research findings", task="Report what the source actually shows.",
                inputs=("assign",), handoff_to="architecture",
                required_next_action="architecture designs against the findings",
            ),
            PlanStep(
                step_id="gate_research", action="gate",
                gate=Gate.RESEARCH_COMPLETENESS.value,
                approver="architecture", subject_author="research",
                evidence_from=("research",), handoff_to="architecture",
            ),
            PlanStep(
                step_id="to_design", action="advance", target_state="design",
                actor="program-manager", task="Findings accepted.",
            ),
            PlanStep(
                step_id="design", action="agent", agent_id="architecture",
                kind=ArtifactKind.ARCHITECTURE_DECISION.value,
                title="Architecture decision", task="Name what is reused and what is new.",
                inputs=("research",), handoff_to="security-governance",
                required_next_action="security reviews the design",
            ),
            PlanStep(
                step_id="gate_design", action="gate",
                gate=Gate.ARCHITECTURE_APPROVAL.value,
                approver="security-governance", subject_author="architecture",
                evidence_from=("design",), handoff_to="security-governance",
            ),
            PlanStep(
                step_id="to_security", action="advance", target_state="security_review",
                actor="program-manager", task="Design approved.",
            ),
            PlanStep(
                step_id="security", action="agent", agent_id="security-governance",
                kind=ArtifactKind.SECURITY_REVIEW.value,
                title="Security review", task="State the authority and execution risk.",
                inputs=("design",), handoff_to="testing-verification",
                required_next_action="testing verifies",
            ),
            PlanStep(
                step_id="gate_security", action="gate",
                gate=Gate.SECURITY_APPROVAL.value,
                approver="security-governance", subject_author="architecture",
                evidence_from=("security",), handoff_to="program-manager",
            ),
            PlanStep(
                step_id="handoff", action="agent", agent_id="program-manager",
                kind=ArtifactKind.IMPLEMENTATION_HANDOFF.value,
                title="Implementation handoff",
                task="Name the scope, the importers and the data shapes.",
                inputs=("design", "security"),
                worktree=REFERENCE_WORKTREE, branch=REFERENCE_BRANCH,
                handoff_to="backend-engineering",
                required_next_action="implementation proceeds in its own worktree",
            ),
            PlanStep(
                step_id="gate_readiness", action="gate",
                gate=Gate.IMPLEMENTATION_READINESS.value,
                approver="architecture", subject_author="program-manager",
                evidence_from=("handoff",), handoff_to="backend-engineering",
            ),
            PlanStep(
                step_id="to_ready", action="advance", target_state="implementation_ready",
                actor="program-manager", task="Handoff accepted.",
            ),
            PlanStep(
                step_id="to_implementation", action="advance",
                target_state="in_implementation",
                actor="program-manager", task="Implementation begins.",
            ),
            PlanStep(
                step_id="review", action="agent", agent_id="code-review",
                kind=ArtifactKind.CODE_REVIEW.value,
                title="Code review", task="Review the implementation candidate.",
                inputs=("handoff",), subject_author="backend-engineering",
                worktree=REFERENCE_WORKTREE, branch=REFERENCE_BRANCH,
                handoff_to="testing-verification",
                required_next_action="testing verifies the reviewed work",
            ),
            PlanStep(
                step_id="gate_code_review", action="gate",
                gate=Gate.CODE_REVIEW.value,
                approver="code-review", subject_author="backend-engineering",
                evidence_from=("review",), handoff_to="testing-verification",
            ),
            PlanStep(
                step_id="to_verification", action="advance", target_state="verification",
                actor="program-manager", task="Review complete.",
            ),
            PlanStep(
                step_id="testing", action="agent", agent_id="testing-verification",
                kind=ArtifactKind.VERIFICATION_REPORT.value,
                title="Verification report", task="Record what ran and what did not.",
                inputs=("review",),
                worktree=REFERENCE_WORKTREE, branch=REFERENCE_BRANCH,
                handoff_to="code-review",
                required_next_action="code review approves the verification",
            ),
            PlanStep(
                step_id="gate_automated", action="gate",
                gate=Gate.AUTOMATED_TESTING.value,
                approver="code-review", subject_author="testing-verification",
                evidence_from=("testing",), handoff_to="code-review",
            ),
            PlanStep(
                step_id="gate_negative", action="gate",
                gate=Gate.NEGATIVE_PATH_TESTING.value,
                approver="code-review", subject_author="testing-verification",
                evidence_from=("testing",), handoff_to="security-governance",
            ),
            PlanStep(
                step_id="redteam", action="agent", agent_id="security-governance",
                kind=ArtifactKind.MEETING_MINUTES.value,
                title="Red-team review minutes",
                task="Record the attack paths considered and any objection.",
                inputs=("testing", "design"), handoff_to="ceo",
                required_next_action="ceo synthesizes the decision",
            ),
            PlanStep(
                step_id="gate_redteam", action="gate",
                gate=Gate.RED_TEAM_REVIEW.value,
                approver="security-governance", subject_author="architecture",
                evidence_from=("redteam",), handoff_to="ceo",
            ),
            PlanStep(
                step_id="to_decision", action="advance", target_state="executive_decision",
                actor="program-manager", task="Verification complete.",
            ),
            PlanStep(
                step_id="docs", action="agent", agent_id="documentation",
                kind=ArtifactKind.DOCUMENTATION_UPDATE.value,
                title="Documentation update", task="Record the runner contract.",
                inputs=("testing",), handoff_to="ceo",
                required_next_action="ceo synthesizes the decision",
            ),
            PlanStep(
                step_id="decision", action="agent", agent_id="ceo",
                kind=ArtifactKind.EXECUTIVE_DECISION.value,
                title="Executive decision", task="Carry the risks into the verdict.",
                inputs=("docs", "redteam"), handoff_to="program-manager",
                required_next_action="program manager reviews the synthesis",
            ),
            PlanStep(
                step_id="gate_synthesis", action="gate",
                gate=Gate.EXECUTIVE_SYNTHESIS.value,
                approver="program-manager", subject_author="ceo",
                evidence_from=("decision",), handoff_to="ceo",
            ),
            PlanStep(
                step_id="verdict", action="verdict", actor="ceo",
                verdict="APPROVED_WITH_LIMITATIONS", handoff_to="owner",
                task="Record the terminal verdict.",
            ),
            PlanStep(
                step_id="close", action="advance", target_state="closed",
                actor="ceo", task="Verdict recorded; the mission closes.",
                handoff_to="owner",
            ),
        ),
    )


def run_reference_mission(
    store_dir: str | Path, *, dev_mission_id: str = REFERENCE_MISSION
) -> dict[str, Any]:
    """Execute the reference plan and return its trace. Offline; no model."""
    runner = AgentRunner(store_dir)
    plan = reference_plan(dev_mission_id=dev_mission_id)
    return runner.run(plan).to_dict()
