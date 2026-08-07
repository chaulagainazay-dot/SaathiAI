"""Agent Orchestration Service — planning/supervision over Mission Runtime."""
from __future__ import annotations

import json
import threading
import time
from typing import Any

from saathi.platform.context import PlatformContextError, PlatformExecutionContext
from saathi.platform.models import PlatformPermission, new_id
from saathi.platform.mission_runtime import (
    MissionRuntimeOrchestrator,
    MissionRuntimeService,
)
from saathi.platform.mission_runtime.models import AgentType, MissionRuntimeState

from .assignment import AgentAssignmentService
from .compiler import PlanCompiler
from .failures import FailureClassifier, RetryPolicy
from .intake import ObjectiveIntakeService
from .models import (
    ACTIVITY_RETENTION,
    MAX_CONCURRENT_MISSIONS,
    MAX_PLAN_VERSIONS,
    MISSION_TO_ORCH,
    ORCHESTRATION_VERSION,
    OrchestrationRecord,
    OrchestrationState,
    TERMINAL_ORCHESTRATION,
    validate_orchestration_transition,
)
from .roles import AgentRoleRegistry
from .templates import list_templates
from .validator import PlanValidator


class AgentOrchestrationService:
    """Central orchestration path.

    Never executes tools directly. Never fabricates approvals. Mission Runtime
    remains authoritative for hierarchy, DAG, checkpoints, evidence, certification.
    """

    def __init__(
        self,
        platform=None,
        *,
        mission_service: MissionRuntimeService | None = None,
        mission_orchestrator: MissionRuntimeOrchestrator | None = None,
        knowledge_service=None,
        conversation_service=None,
    ):
        if platform is None:
            from saathi.platform.service import default_platform

            platform = default_platform()
        self.platform = platform
        self.store = platform.store
        self.mission = mission_service or MissionRuntimeService(platform)
        self.mission_orch = mission_orchestrator or MissionRuntimeOrchestrator(platform)
        self.knowledge = knowledge_service
        self.conversation = conversation_service
        self.roles = AgentRoleRegistry()
        self.intake_svc = ObjectiveIntakeService()
        self.compiler = PlanCompiler(self.roles)
        self.validator = PlanValidator(self.roles)
        self.assignment = AgentAssignmentService(self.roles)
        self.failures = FailureClassifier()
        self._lock = threading.RLock()
        self._records: dict[str, OrchestrationRecord] = {}
        self._by_mission: dict[str, str] = {}
        self._active_runs = 0

    # ── helpers ──────────────────────────────────────────────────────────
    def _audit(self, ctx, event: str, **detail) -> None:
        safe = {
            k: v
            for k, v in detail.items()
            if k not in {"prompt", "token", "password", "authorization", "raw"}
        }
        self.store.append_audit(
            event,
            user_id=getattr(ctx, "user_id", "") or "",
            role=getattr(ctx, "role", "") or "",
            org_id=getattr(ctx, "org_id", "") or "",
            workspace_id=getattr(ctx, "workspace_id", "") or "",
            project_id=getattr(ctx, "project_id", "") or "",
            mission_id=str(detail.get("mission_id") or ""),
            outcome=str(detail.get("outcome") or "success"),
            detail=safe,
        )

    def _activity(self, rec: OrchestrationRecord, kind: str, message: str, **extra) -> None:
        rec.activity.append(
            {
                "ts": time.time(),
                "kind": kind,
                "message": message[:500],
                **{k: v for k, v in extra.items() if k not in {"raw", "prompt"}},
            }
        )
        if len(rec.activity) > ACTIVITY_RETENTION:
            rec.activity = rec.activity[-ACTIVITY_RETENTION:]
        rec.updated_at = time.time()

    def _transition(self, rec: OrchestrationRecord, new_state: str) -> None:
        if rec.state == new_state:
            return
        validate_orchestration_transition(rec.state, new_state)
        rec.state = new_state
        rec.updated_at = time.time()

    def _get(self, orchestration_id: str, ctx: PlatformExecutionContext) -> OrchestrationRecord:
        with self._lock:
            rec = self._records.get(orchestration_id)
        if not rec:
            raise PlatformContextError("NOT_FOUND", "orchestration not found")
        if rec.org_id != ctx.org_id or rec.workspace_id != ctx.workspace_id:
            raise PlatformContextError("NOT_FOUND", "orchestration not accessible")
        return rec

    def _count_active_for_tenant(self, org_id: str, workspace_id: str) -> int:
        with self._lock:
            return sum(
                1
                for r in self._records.values()
                if r.org_id == org_id
                and r.workspace_id == workspace_id
                and r.state not in {s.value for s in TERMINAL_ORCHESTRATION}
                and r.state not in {OrchestrationState.DRAFT.value}
            )

    def _ground_context(self, ctx, objective: str) -> dict[str, Any]:
        out: dict[str, Any] = {
            "grounded": False,
            "text": "",
            "citations": [],
            "claim_kinds": [],
        }
        if self.knowledge is None:
            try:
                from saathi.platform.knowledge import default_knowledge_service

                self.knowledge = default_knowledge_service(self.platform)
            except Exception:
                return out
        try:
            if hasattr(self.knowledge, "should_ground") and self.knowledge.should_ground(
                objective, yeti_mode="project"
            ):
                g = self.knowledge.ground(ctx, objective, domain="project")
                out = {
                    "grounded": bool(g.grounded),
                    "text": (g.prompt_block or "")[:4000],
                    "citations": [c.to_public() for c in g.citations[:8]],
                    "no_evidence": g.no_evidence,
                    "claim_kind": g.claim_kind,
                }
        except Exception:
            out["error"] = "knowledge_unavailable"
        return out

    # ── public API ───────────────────────────────────────────────────────
    def health(self, ctx: PlatformExecutionContext) -> dict[str, Any]:
        ctx.require_permission(PlatformPermission.MISSION_READ)
        with self._lock:
            records = [
                r
                for r in self._records.values()
                if r.org_id == ctx.org_id and r.workspace_id == ctx.workspace_id
            ]
        by_state: dict[str, int] = {}
        for r in records:
            by_state[r.state] = by_state.get(r.state, 0) + 1
        knowledge_ready = False
        if self.knowledge is not None:
            try:
                knowledge_ready = bool(self.knowledge.index.count_chunks() > 0)
            except Exception:
                knowledge_ready = False
        return {
            "service": "agent_orchestration",
            "version": ORCHESTRATION_VERSION,
            "ready": True,
            "active_orchestrations": sum(
                1
                for r in records
                if r.state not in {s.value for s in TERMINAL_ORCHESTRATION}
            ),
            "states": by_state,
            "roles": len(self.roles.list_roles()),
            "templates": len(list_templates()),
            "knowledge_ready": knowledge_ready,
            "mission_runtime": "authoritative",
            "execution_gateway": "PlatformAgentRuntime→ExecutionGateway",
            "tools_executable_by_model": False,
            "production_authorized": False,
            "max_concurrent_missions": MAX_CONCURRENT_MISSIONS,
            "bounds": {
                "max_plan_nodes": 200,
                "max_retries": 5,
                "max_parallel_tasks": 8,
            },
        }

    def list_roles(self, ctx: PlatformExecutionContext) -> list[dict[str, Any]]:
        ctx.require_permission(PlatformPermission.MISSION_READ)
        return self.roles.list_roles()

    def list_templates(self, ctx: PlatformExecutionContext) -> list[dict[str, Any]]:
        ctx.require_permission(PlatformPermission.MISSION_READ)
        return list_templates()

    def intake(self, ctx: PlatformExecutionContext, payload: dict[str, Any]) -> dict[str, Any]:
        ctx.require_permission(PlatformPermission.MISSION_WRITE)
        try:
            intake = self.intake_svc.parse(payload, ctx=ctx)
        except ValueError as exc:
            raise PlatformContextError("VALIDATION_FAILED", str(exc)) from exc
        grounded = self._ground_context(ctx, intake.objective)
        self._audit(
            ctx,
            "orchestration.intake",
            outcome="success",
            template_id=intake.template_id,
            ambiguities=len(intake.ambiguities),
            grounded=grounded.get("grounded"),
        )
        return {
            "intake": intake.to_public(),
            "ready": intake.is_ready(),
            "grounding": {
                "grounded": grounded.get("grounded"),
                "citation_count": len(grounded.get("citations") or []),
                "no_evidence": grounded.get("no_evidence"),
                "claim_kind": grounded.get("claim_kind"),
            },
            "suggested_template": intake.template_id,
        }

    def compile_plan(
        self,
        ctx: PlatformExecutionContext,
        payload: dict[str, Any],
        *,
        model_proposal: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ctx.require_permission(PlatformPermission.MISSION_WRITE)
        try:
            intake = self.intake_svc.parse(payload.get("intake") or payload, ctx=ctx)
        except ValueError as exc:
            raise PlatformContextError("VALIDATION_FAILED", str(exc)) from exc
        grounded = self._ground_context(ctx, intake.objective)
        plan = self.compiler.compile(
            intake,
            model_proposal=model_proposal or payload.get("model_proposal"),
            grounded_context=str(grounded.get("text") or ""),
        )
        assignments = self.assignment.assign_plan(plan)
        validation = self.validator.validate(plan)
        self._audit(
            ctx,
            "orchestration.plan_compiled",
            outcome="success" if validation.ok else "validation_failed",
            node_count=validation.node_count,
            errors=len(validation.errors),
        )
        return {
            "plan": plan,
            "assignments": assignments,
            "validation": validation.to_public(),
            "grounding": {
                "grounded": grounded.get("grounded"),
                "citations": grounded.get("citations") or [],
            },
            "intake": intake.to_public(),
        }

    def validate_plan(
        self, ctx: PlatformExecutionContext, plan: dict[str, Any]
    ) -> dict[str, Any]:
        ctx.require_permission(PlatformPermission.MISSION_READ)
        result = self.validator.validate(plan or {})
        return {"validation": result.to_public()}

    def create(
        self,
        ctx: PlatformExecutionContext,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Create mission + validated plan + orchestration record."""
        ctx.require_permission(PlatformPermission.MISSION_WRITE)
        if self._count_active_for_tenant(ctx.org_id, ctx.workspace_id) >= MAX_CONCURRENT_MISSIONS:
            raise PlatformContextError(
                "RESOURCE_BUDGET_EXHAUSTED",
                f"concurrent orchestration limit {MAX_CONCURRENT_MISSIONS}",
            )

        compiled = self.compile_plan(ctx, payload)
        if not compiled["validation"]["ok"]:
            raise PlatformContextError(
                "VALIDATION_FAILED",
                "; ".join(compiled["validation"]["errors"][:5]) or "plan invalid",
            )
        plan = compiled["plan"]
        intake = compiled["intake"]

        # Ensure project/mission
        project_id = str(payload.get("project_id") or ctx.project_id or "")
        if not project_id:
            project = self.platform.create_project(
                ctx, f"Orchestration: {(intake.get('objective') or '')[:60]}"
            )
            project_id = project["project_id"]
        mission_id = str(payload.get("mission_id") or "")
        if not mission_id:
            # create_mission may need project on context
            mission_ctx = PlatformExecutionContext(
                user_id=ctx.user_id,
                role=ctx.role,
                org_id=ctx.org_id,
                workspace_id=ctx.workspace_id,
                project_id=project_id,
            )
            mission_key = f"ORCH-{new_id('')[:10]}"
            mission = self.platform.create_mission(
                mission_ctx,
                project_id,
                mission_key,
                (intake.get("objective") or "Orchestrated mission")[:120],
            )
            mission_id = mission["mission_id"]

        mission_ctx = PlatformExecutionContext(
            user_id=ctx.user_id,
            role=ctx.role,
            org_id=ctx.org_id,
            workspace_id=ctx.workspace_id,
            project_id=project_id,
            mission_id=mission_id,
        )
        # Persist plan via Mission Runtime (authoritative)
        planned = self.mission.plan(mission_ctx, mission_id, plan)

        orch_id = new_id("orch_")
        rec = OrchestrationRecord(
            orchestration_id=orch_id,
            mission_id=mission_id,
            org_id=ctx.org_id,
            workspace_id=ctx.workspace_id,
            project_id=project_id,
            user_id=ctx.user_id,
            state=OrchestrationState.READY.value,
            objective=str(intake.get("objective") or ""),
            plan_version=1,
            template_id=str(plan.get("template_id") or ""),
            domain=str(plan.get("domain") or "engineering"),
            risk_level=str(plan.get("risk_level") or "medium"),
            production_impact=bool(plan.get("production_impact")),
            intake=intake,
            plan_definition=plan,
            validation=compiled["validation"],
            assignments=compiled["assignments"],
            last_checkpoint_id=str(
                (planned.get("checkpoint") or {}).get("checkpoint_id")
                or (planned.get("runtime") or {}).get("last_checkpoint_id")
                or ""
            ),
        )
        # Prefer checkpoint from plan response
        if not rec.last_checkpoint_id:
            snap = self.mission.get(mission_ctx, mission_id)
            cps = snap.get("checkpoints") or []
            if cps:
                rec.last_checkpoint_id = cps[-1].get("checkpoint_id", "")

        self._activity(rec, "created", "Orchestration created with validated plan")
        self._activity(
            rec,
            "planned",
            f"Mission plan accepted with {compiled['validation']['node_count']} nodes",
        )
        with self._lock:
            self._records[orch_id] = rec
            self._by_mission[mission_id] = orch_id

        self._audit(
            ctx,
            "orchestration.created",
            outcome="success",
            mission_id=mission_id,
            orchestration_id=orch_id,
            plan_version=1,
        )
        return self.get(ctx, orch_id)

    def get(self, ctx: PlatformExecutionContext, orchestration_id: str) -> dict[str, Any]:
        ctx.require_permission(PlatformPermission.MISSION_READ)
        rec = self._get(orchestration_id, ctx)
        mission_snap = None
        try:
            mctx = PlatformExecutionContext(
                user_id=ctx.user_id,
                role=ctx.role,
                org_id=ctx.org_id,
                workspace_id=ctx.workspace_id,
                project_id=rec.project_id,
                mission_id=rec.mission_id,
            )
            mission_snap = self.mission.get(mctx, rec.mission_id)
            # Sync display state from mission when running
            mstate = str((mission_snap.get("runtime") or {}).get("state") or "")
            mapped = MISSION_TO_ORCH.get(mstate)
            if mapped and rec.state not in {s.value for s in TERMINAL_ORCHESTRATION}:
                if mapped != rec.state and rec.state not in {
                    OrchestrationState.DRAFT.value,
                    OrchestrationState.VALIDATING.value,
                }:
                    # soft sync without strict transition when mission advanced
                    if mapped in {
                        OrchestrationState.RUNNING.value,
                        OrchestrationState.WAITING_APPROVAL.value,
                        OrchestrationState.BLOCKED.value,
                        OrchestrationState.PAUSED.value,
                        OrchestrationState.COMPLETED.value,
                        OrchestrationState.FAILED.value,
                        OrchestrationState.CANCELLED.value,
                        OrchestrationState.CERTIFIED.value,
                    }:
                        rec.state = mapped
        except Exception:
            mission_snap = None
        public = rec.to_public()
        public["mission"] = {
            "mission_id": rec.mission_id,
            "state": (mission_snap or {}).get("runtime", {}).get("state"),
            "dashboard": (mission_snap or {}).get("dashboard"),
            "task_counts": (mission_snap or {}).get("dashboard", {}).get("task_counts"),
            "progress_percent": (mission_snap or {}).get("dashboard", {}).get(
                "progress_percent"
            ),
        }
        if mission_snap:
            public["graph"] = {
                "tasks": mission_snap.get("tasks") or [],
                "dependencies": mission_snap.get("dependencies") or [],
                "hierarchy": mission_snap.get("hierarchy") or [],
            }
            public["checkpoints"] = (mission_snap.get("checkpoints") or [])[-10:]
            public["evidence"] = (mission_snap.get("evidence") or [])[-20:]
            public["decisions"] = (mission_snap.get("decisions") or [])[-20:]
            public["blockers"] = (mission_snap.get("runtime") or {}).get(
                "known_blockers"
            ) or []
        return {"orchestration": public}

    def list(self, ctx: PlatformExecutionContext, *, limit: int = 50) -> dict[str, Any]:
        ctx.require_permission(PlatformPermission.MISSION_READ)
        lim = max(1, min(int(limit), 100))
        with self._lock:
            items = [
                r
                for r in self._records.values()
                if r.org_id == ctx.org_id and r.workspace_id == ctx.workspace_id
            ]
        items.sort(key=lambda r: r.updated_at, reverse=True)
        return {
            "orchestrations": [
                {
                    "orchestration_id": r.orchestration_id,
                    "mission_id": r.mission_id,
                    "state": r.state,
                    "objective": r.objective[:200],
                    "plan_version": r.plan_version,
                    "template_id": r.template_id,
                    "updated_at": r.updated_at,
                }
                for r in items[:lim]
            ]
        }

    def start(
        self, ctx: PlatformExecutionContext, orchestration_id: str, *, token: str = ""
    ) -> dict[str, Any]:
        ctx.require_permission(PlatformPermission.MISSION_RUN)
        rec = self._get(orchestration_id, ctx)
        if rec.state not in {
            OrchestrationState.READY.value,
            OrchestrationState.PAUSED.value,
        }:
            raise PlatformContextError(
                "INVALID_STATE", f"cannot start from {rec.state}"
            )
        # Check blocked policy nodes
        for task in self.compiler._iter_tasks(rec.plan_definition):
            if task.get("approval_requirement") == "BLOCKED_BY_POLICY":
                self._transition(rec, OrchestrationState.BLOCKED.value)
                rec.failure_class = "SECURITY_GATE"
                self._activity(rec, "blocked", task.get("blocked_reason") or "policy block")
                raise PlatformContextError(
                    "PROHIBITED", task.get("blocked_reason") or "blocked by policy"
                )

        mctx = PlatformExecutionContext(
            user_id=ctx.user_id,
            role=ctx.role,
            org_id=ctx.org_id,
            workspace_id=ctx.workspace_id,
            project_id=rec.project_id,
            mission_id=rec.mission_id,
        )
        self._transition(rec, OrchestrationState.RUNNING.value)
        self._activity(rec, "started", "Orchestration run started")
        try:
            report = self.mission_orch.run_until_stop(
                mctx, rec.mission_id, token=token or ""
            )
        except PlatformContextError:
            raise
        except Exception as exc:
            fc = self.failures.classify(message=str(exc))
            rec.failure_class = fc.value
            action = self.failures.action_for(fc)
            self._activity(rec, "failure", f"{fc.value}: {exc}", action=action.value)
            if action.value == "fail_closed":
                self._transition(rec, OrchestrationState.FAILED.value)
            else:
                self._transition(rec, OrchestrationState.BLOCKED.value)
            raise PlatformContextError("ORCHESTRATION_FAILED", str(exc)) from exc

        # Map stop into orchestration state
        stop = str(report.get("stop_condition") or "")
        snap = self.mission.get(mctx, rec.mission_id)
        mstate = str((snap.get("runtime") or {}).get("state") or "")
        if mstate == MissionRuntimeState.COMPLETED.value:
            self._transition(rec, OrchestrationState.COMPLETED.value)
        elif mstate == MissionRuntimeState.WAITING.value:
            self._transition(rec, OrchestrationState.WAITING_APPROVAL.value)
        elif mstate == MissionRuntimeState.BLOCKED.value:
            self._transition(rec, OrchestrationState.BLOCKED.value)
        elif mstate == MissionRuntimeState.FAILED.value:
            self._transition(rec, OrchestrationState.FAILED.value)
        elif mstate == MissionRuntimeState.PAUSED.value:
            self._transition(rec, OrchestrationState.PAUSED.value)
        elif mstate == MissionRuntimeState.CANCELLED.value:
            self._transition(rec, OrchestrationState.CANCELLED.value)
        self._activity(rec, "cycle", f"run_until_stop: {stop or mstate}")
        self._audit(
            ctx,
            "orchestration.started",
            outcome="success",
            mission_id=rec.mission_id,
            orchestration_id=rec.orchestration_id,
            stop_condition=stop,
        )
        result = self.get(ctx, orchestration_id)
        result["run_report"] = {
            "stop_condition": stop,
            "mission_state": mstate,
            "progress": report.get("progress"),
        }
        return result

    def pause(self, ctx: PlatformExecutionContext, orchestration_id: str) -> dict[str, Any]:
        ctx.require_permission(PlatformPermission.MISSION_RUN)
        rec = self._get(orchestration_id, ctx)
        mctx = PlatformExecutionContext(
            user_id=ctx.user_id,
            role=ctx.role,
            org_id=ctx.org_id,
            workspace_id=ctx.workspace_id,
            project_id=rec.project_id,
            mission_id=rec.mission_id,
        )
        self.mission_orch.pause(mctx, rec.mission_id, reason="operator pause")
        if rec.state not in {s.value for s in TERMINAL_ORCHESTRATION}:
            try:
                self._transition(rec, OrchestrationState.PAUSED.value)
            except ValueError:
                rec.state = OrchestrationState.PAUSED.value
        self._activity(rec, "paused", "Paused by operator")
        return self.get(ctx, orchestration_id)

    def resume(
        self, ctx: PlatformExecutionContext, orchestration_id: str, *, token: str = ""
    ) -> dict[str, Any]:
        ctx.require_permission(PlatformPermission.MISSION_RUN)
        rec = self._get(orchestration_id, ctx)
        mctx = PlatformExecutionContext(
            user_id=ctx.user_id,
            role=ctx.role,
            org_id=ctx.org_id,
            workspace_id=ctx.workspace_id,
            project_id=rec.project_id,
            mission_id=rec.mission_id,
        )
        self.mission_orch.resume(mctx, rec.mission_id)
        rec.state = OrchestrationState.RUNNING.value
        self._activity(rec, "resumed", "Resumed by operator")
        return self.start(ctx, orchestration_id, token=token)

    def cancel(self, ctx: PlatformExecutionContext, orchestration_id: str) -> dict[str, Any]:
        ctx.require_permission(PlatformPermission.MISSION_RUN)
        rec = self._get(orchestration_id, ctx)
        mctx = PlatformExecutionContext(
            user_id=ctx.user_id,
            role=ctx.role,
            org_id=ctx.org_id,
            workspace_id=ctx.workspace_id,
            project_id=rec.project_id,
            mission_id=rec.mission_id,
        )
        try:
            self.mission_orch.cancel(mctx, rec.mission_id, token="")
        except PlatformContextError:
            pass
        rec.state = OrchestrationState.CANCELLED.value
        self._activity(rec, "cancelled", "Cancelled by operator")
        self._audit(
            ctx,
            "orchestration.cancelled",
            mission_id=rec.mission_id,
            orchestration_id=rec.orchestration_id,
        )
        return self.get(ctx, orchestration_id)

    def replan(
        self,
        ctx: PlatformExecutionContext,
        orchestration_id: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Bounded replan: new plan version, supersede via mission plan replace only when PLANNED/DRAFT.

        If mission already advanced, replan records a new definition version for audit
        but does not rewrite completed task history.
        """
        ctx.require_permission(PlatformPermission.MISSION_WRITE)
        rec = self._get(orchestration_id, ctx)
        if rec.plan_version >= MAX_PLAN_VERSIONS:
            raise PlatformContextError(
                "RESOURCE_BUDGET_EXHAUSTED", "plan version budget exhausted"
            )
        payload = payload or {}
        base_intake = dict(rec.intake)
        base_intake.update(payload.get("intake") or payload)
        if not base_intake.get("objective"):
            base_intake["objective"] = rec.objective
        compiled = self.compile_plan(ctx, base_intake)
        if not compiled["validation"]["ok"]:
            raise PlatformContextError(
                "VALIDATION_FAILED",
                "; ".join(compiled["validation"]["errors"][:5]),
            )
        # Preserve history: store previous version marker
        prev = {
            "plan_version": rec.plan_version,
            "superseded_at": time.time(),
            "reason": str(payload.get("reason") or "operator_replan")[:300],
        }
        rec.activity.append({"ts": time.time(), "kind": "supersede", "previous": prev})
        rec.plan_version += 1
        rec.plan_definition = compiled["plan"]
        rec.validation = compiled["validation"]
        rec.assignments = compiled["assignments"]
        rec.intake = compiled["intake"]

        mctx = PlatformExecutionContext(
            user_id=ctx.user_id,
            role=ctx.role,
            org_id=ctx.org_id,
            workspace_id=ctx.workspace_id,
            project_id=rec.project_id,
            mission_id=rec.mission_id,
        )
        # Only replace mission plan when still draft/planned
        try:
            snap = self.mission.get(mctx, rec.mission_id)
            state = str((snap.get("runtime") or {}).get("state") or "")
            if state in {
                MissionRuntimeState.DRAFT.value,
                MissionRuntimeState.PLANNED.value,
            }:
                self.mission.plan(mctx, rec.mission_id, compiled["plan"])
                rec.state = OrchestrationState.READY.value
            else:
                rec.limitations.append(
                    "replan recorded without rewriting in-progress mission history"
                )
                self._activity(
                    rec,
                    "replan_deferred",
                    f"Mission in {state}; plan version stored without history rewrite",
                )
        except PlatformContextError as exc:
            rec.limitations.append(f"replan mission apply limited: {exc.code}")
        self._activity(
            rec, "replanned", f"Plan version {rec.plan_version} validated"
        )
        self._audit(
            ctx,
            "orchestration.replanned",
            mission_id=rec.mission_id,
            orchestration_id=rec.orchestration_id,
            plan_version=rec.plan_version,
        )
        return self.get(ctx, orchestration_id)

    def recover(
        self, ctx: PlatformExecutionContext, orchestration_id: str, *, token: str = ""
    ) -> dict[str, Any]:
        ctx.require_permission(PlatformPermission.MISSION_RUN)
        rec = self._get(orchestration_id, ctx)
        mctx = PlatformExecutionContext(
            user_id=ctx.user_id,
            role=ctx.role,
            org_id=ctx.org_id,
            workspace_id=ctx.workspace_id,
            project_id=rec.project_id,
            mission_id=rec.mission_id,
        )
        rec.state = OrchestrationState.RECOVERING.value
        self._activity(rec, "recovering", "Recovery from last checkpoint")
        try:
            self.mission_orch.recover(mctx, rec.mission_id, token=token)
        except TypeError:
            try:
                self.mission_orch.recover(mctx, rec.mission_id)
            except Exception as exc:
                fc = self.failures.classify(message=str(exc))
                if "stale" in str(exc).lower() or fc.value == "RECOVERY_MISMATCH":
                    rec.failure_class = "RECOVERY_MISMATCH"
                    rec.state = OrchestrationState.FAILED.value
                    raise PlatformContextError("RECOVERY_MISMATCH", str(exc)) from exc
                raise
        except Exception as exc:
            fc = self.failures.classify(message=str(exc))
            if fc.value == "RECOVERY_MISMATCH" or "stale" in str(exc).lower():
                rec.failure_class = "RECOVERY_MISMATCH"
                rec.state = OrchestrationState.FAILED.value
                raise PlatformContextError("RECOVERY_MISMATCH", str(exc)) from exc
            raise
        rec.state = OrchestrationState.READY.value
        self._activity(rec, "recovered", "Recovery completed; ready to resume")
        return self.get(ctx, orchestration_id)

    def checkpoint(
        self, ctx: PlatformExecutionContext, orchestration_id: str
    ) -> dict[str, Any]:
        ctx.require_permission(PlatformPermission.MISSION_WRITE)
        rec = self._get(orchestration_id, ctx)
        mctx = PlatformExecutionContext(
            user_id=ctx.user_id,
            role=ctx.role,
            org_id=ctx.org_id,
            workspace_id=ctx.workspace_id,
            project_id=rec.project_id,
            mission_id=rec.mission_id,
        )
        cp = self.mission.create_checkpoint(
            mctx,
            rec.mission_id,
            created_by=AgentType.OPERATOR.value,
        )
        rec.last_checkpoint_id = cp.get("checkpoint_id") or cp.get("checkpoint", {}).get(
            "checkpoint_id", ""
        )
        if not rec.last_checkpoint_id and isinstance(cp.get("checkpoint"), dict):
            rec.last_checkpoint_id = cp["checkpoint"].get("checkpoint_id", "")
        self._activity(
            rec, "checkpoint", f"Checkpoint {rec.last_checkpoint_id or 'created'}"
        )
        return {"checkpoint": cp, "orchestration": self.get(ctx, orchestration_id)["orchestration"]}

    def certify(
        self,
        ctx: PlatformExecutionContext,
        orchestration_id: str,
        *,
        with_limitations: bool = False,
        summary: str = "",
        limitations: list[str] | None = None,
    ) -> dict[str, Any]:
        ctx.require_permission(PlatformPermission.MISSION_WRITE)
        rec = self._get(orchestration_id, ctx)
        if rec.state not in {
            OrchestrationState.COMPLETED.value,
            OrchestrationState.CERTIFYING.value,
            OrchestrationState.READY.value,  # planning-only may complete early
            OrchestrationState.BLOCKED.value,
        }:
            # Allow certify from completed mission even if orch state lagging
            pass
        mctx = PlatformExecutionContext(
            user_id=ctx.user_id,
            role=ctx.role,
            org_id=ctx.org_id,
            workspace_id=ctx.workspace_id,
            project_id=rec.project_id,
            mission_id=rec.mission_id,
        )
        snap = self.mission.get(mctx, rec.mission_id)
        evidence = snap.get("evidence") or []
        if not evidence and not with_limitations:
            raise PlatformContextError(
                "EVIDENCE_MISSING",
                "certification requires evidence or explicit limitations",
            )
        # Independent review check
        tasks = snap.get("tasks") or []
        has_review = any(
            t.get("agent_type") in {"ReviewerAgent", "CertificationAgent", "SecurityAgent"}
            and t.get("status") == "COMPLETED"
            for t in tasks
        )
        lims = list(limitations or rec.limitations)
        if not has_review:
            lims.append("no independent review task completed")
            with_limitations = True
        if rec.production_impact:
            lims.append("production impact plans never authorize production")
            with_limitations = True
        lims.append("local orchestration only; production not authorized")

        rec.state = OrchestrationState.CERTIFYING.value
        verdict = "MISSION_COMPLETE"
        safe_summary = (summary or "Orchestration certified from mission evidence")[:1000]
        evidence_ids = [
            e.get("evidence_id") for e in evidence if e.get("evidence_id")
        ][:20]
        try:
            if not evidence_ids:
                raise PlatformContextError("EVIDENCE_MISSING", "no evidence ids")
            cert = self.mission.certify(
                mctx,
                rec.mission_id,
                verdict=verdict,
                summary=safe_summary,
                evidence_ids=evidence_ids,
                limitations=lims[:20],
            )
        except PlatformContextError:
            # Fall back to orchestration-level cert with limitations when mission
            # is not COMPLETED or evidence gate not fully satisfied.
            cert = {
                "certification_id": new_id("ocert_"),
                "verdict": "ORCHESTRATION_CERTIFIED_WITH_LIMITATIONS",
                "summary": safe_summary,
                "limitations": lims,
                "mission_state": (snap.get("runtime") or {}).get("state"),
                "evidence_count": len(evidence),
            }
            with_limitations = True

        rec.certification = cert if isinstance(cert, dict) else {"raw": str(cert)}
        rec.limitations = lims
        rec.state = (
            OrchestrationState.CERTIFIED_WITH_LIMITATIONS.value
            if with_limitations
            else OrchestrationState.CERTIFIED.value
        )
        self._activity(rec, "certified", rec.state)
        self._audit(
            ctx,
            "orchestration.certified",
            mission_id=rec.mission_id,
            orchestration_id=rec.orchestration_id,
            with_limitations=with_limitations,
        )
        return self.get(ctx, orchestration_id)

    def classify_failure(
        self, ctx: PlatformExecutionContext, payload: dict[str, Any]
    ) -> dict[str, Any]:
        ctx.require_permission(PlatformPermission.MISSION_READ)
        fc = self.failures.classify(
            error_code=str(payload.get("error_code") or ""),
            message=str(payload.get("message") or ""),
            outcome=str(payload.get("outcome") or ""),
        )
        action = self.failures.action_for(fc)
        policy = self.failures.default_retry_policy(
            int(payload.get("max_attempts") or 2)
        )
        return {
            "failure_class": fc.value,
            "action": action.value,
            "retry_allowed": policy.allows(fc),
            "retry_policy": policy.to_public(),
        }

    def command_from_conversation(
        self, ctx: PlatformExecutionContext, message: str, *, orchestration_id: str = ""
    ) -> dict[str, Any]:
        """Map natural-language control intents to operator commands (RBAC still applies)."""
        ctx.require_permission(PlatformPermission.MISSION_READ)
        m = (message or "").lower().strip()
        if not m:
            raise PlatformContextError("VALIDATION_FAILED", "message required")
        intent = "unknown"
        if any(x in m for x in ("pause", "hold")):
            intent = "pause"
        elif any(x in m for x in ("resume", "continue")):
            intent = "resume"
        elif any(x in m for x in ("cancel", "abort", "stop mission")):
            intent = "cancel"
        elif any(x in m for x in ("replan", "change plan")):
            intent = "replan"
        elif any(x in m for x in ("checkpoint",)):
            intent = "checkpoint"
        elif any(x in m for x in ("why blocked", "blocked", "blocker")):
            intent = "inspect_blockers"
        elif any(x in m for x in ("approval", "approve")):
            intent = "inspect_approvals"
        elif any(x in m for x in ("plan this", "create plan", "plan a")):
            intent = "create"
        elif any(x in m for x in ("start", "run mission", "execute plan")):
            intent = "start"
        # Never execute from chat without explicit orchestration_id for control ops
        result: dict[str, Any] = {
            "intent": intent,
            "requires_orchestration_id": intent
            in {"pause", "resume", "cancel", "replan", "checkpoint", "start"},
            "executed": False,
            "note": "Conversation proposes commands only; RBAC and mission authority still apply.",
        }
        if orchestration_id and intent in {
            "pause",
            "resume",
            "cancel",
            "checkpoint",
            "inspect_blockers",
            "inspect_approvals",
        }:
            if intent == "pause":
                result["result"] = self.pause(ctx, orchestration_id)
                result["executed"] = True
            elif intent == "cancel":
                result["result"] = self.cancel(ctx, orchestration_id)
                result["executed"] = True
            elif intent == "checkpoint":
                result["result"] = self.checkpoint(ctx, orchestration_id)
                result["executed"] = True
            elif intent in {"inspect_blockers", "inspect_approvals"}:
                result["result"] = self.get(ctx, orchestration_id)
                result["executed"] = True
        return result


_DEFAULT: AgentOrchestrationService | None = None
_LOCK = threading.Lock()


def default_orchestration_service(platform_service=None) -> AgentOrchestrationService:
    global _DEFAULT
    with _LOCK:
        if platform_service is not None:
            existing = getattr(platform_service, "_orchestration_service", None)
            if existing is not None:
                return existing
            svc = AgentOrchestrationService(platform_service)
            setattr(platform_service, "_orchestration_service", svc)
            return svc
        if _DEFAULT is None:
            _DEFAULT = AgentOrchestrationService()
        return _DEFAULT


def reset_orchestration_service_for_tests(platform_service=None) -> None:
    global _DEFAULT
    with _LOCK:
        _DEFAULT = None
        if platform_service is not None and hasattr(
            platform_service, "_orchestration_service"
        ):
            delattr(platform_service, "_orchestration_service")
