"""M20.0 — Governed Engineering Orchestrator (control plane, not a coding agent)."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from saathi.config import ROOT
from saathi.engineering.adapters import get_adapter
from saathi.engineering.adapters.base import LaunchRequest
from saathi.engineering.commit_verify import verify_commit
from saathi.engineering.handoff import HandoffManager, HandoffPayload
from saathi.engineering.models import (
    Checkpoint,
    EngineeringBacklogItem,
    EngineeringTask,
    ItemStatus,
    SessionPhase,
    SessionStatus,
    Verdict,
    new_id,
)
from saathi.engineering.monitor import ProgressMonitor
from saathi.engineering.prompt_builder import build_engineering_prompt
from saathi.engineering.push_verify import perform_push, pre_push_check
from saathi.engineering.readiness import check_repository_readiness
from saathi.engineering.retry import RetryController
from saathi.engineering.security import (
    permission_for_action,
    trading_guardian_isolation_report,
)
from saathi.engineering.selector import select_candidate
from saathi.engineering.settings import EngineeringSettings, disable_procedure, load_settings
from saathi.engineering.stop_policy import StopPolicy
from saathi.engineering.store import EngineeringStore
from saathi.engineering.validation import ValidationCoordinator


@dataclass
class OrchestratorResult:
    ok: bool
    verdict: str
    item_id: str = ""
    task_id: str = ""
    session_id: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "verdict": self.verdict,
            "item_id": self.item_id,
            "task_id": self.task_id,
            "session_id": self.session_id,
            "details": self.details,
        }


class EngineeringOrchestrator:
    """Supervise engineering missions; coordinate existing systems only."""

    def __init__(
        self,
        settings: EngineeringSettings | None = None,
        store: EngineeringStore | None = None,
        repository_root: str | Path | None = None,
    ):
        self.settings = settings or load_settings()
        self.root = Path(repository_root or ROOT).resolve()
        self.store = store or EngineeringStore(self.settings.store_path())
        self.monitor = ProgressMonitor(
            self.store, stall_timeout_sec=self.settings.stall_timeout_sec
        )
        self.retry = RetryController(max_retries=self.settings.max_retries)
        self.stop_policy = StopPolicy()
        self.handoff_mgr = HandoffManager(self.root)

    # ---- read-only ops (allowed even when disabled) ----
    def status(self) -> dict[str, Any]:
        return {
            "settings": self.settings.to_dict(),
            "backlog_count": len(self.store.list_items()),
            "active_sessions": self.store.active_session_count(),
            "repository_root": str(self.root),
            "trading_guardian": trading_guardian_isolation_report(),
            "enabled": self.settings.orchestrator_enabled,
        }

    def backlog(self) -> list[dict[str, Any]]:
        return [i.to_dict() for i in self.store.list_items()]

    def inspect(self, item_id: str) -> dict[str, Any]:
        item = self.store.get_item(item_id)
        if not item:
            return {"error": "not_found", "item_id": item_id}
        deps_ok, deps = self.store.dependency_ready(item)
        return {
            "item": item.to_dict(),
            "dependencies_ok": deps_ok,
            "dependency_issues": deps,
        }

    def readiness(self, expected_branch: str | None = None) -> dict[str, Any]:
        rep = check_repository_readiness(
            self.root,
            self.settings,
            expected_branch=expected_branch,
            active_writer=self.store.active_session_count() > 0
            and self.settings.repository_writes_enabled,
        )
        return rep.to_dict()

    def select(self) -> dict[str, Any]:
        ready = check_repository_readiness(self.root, self.settings)
        result = select_candidate(
            self.store,
            repo_clean=ready.checks.get("dirty_count", 0) == 0,
            readiness_state=ready.state,
        )
        return result.to_dict()

    def plan(self, item_id: str, *, knowledge_context: str = "") -> dict[str, Any]:
        item = self.store.get_item(item_id)
        if not item:
            return {"error": "not_found"}
        ready = check_repository_readiness(self.root, self.settings)
        task = EngineeringTask(
            task_id=new_id("task"),
            item_id=item.item_id,
            objective=item.title + "\n" + item.description,
            scope=list(item.acceptance_criteria),
            out_of_scope=list(item.out_of_scope),
            starting_commit=ready.head,
            branch=ready.branch,
            repository_root=str(self.root),
            validation_plan=list(item.required_validations),
        )
        self.store.save_task(task)
        approval = "required" if item.approval_requirement else "not_required"
        prompt = build_engineering_prompt(
            item,
            task,
            knowledge_context=knowledge_context,
            approval_state=approval,
        )
        return {
            "task": task.to_dict(),
            "prompt": prompt.to_dict(),
            "readiness": ready.to_dict(),
        }

    def checkpoint(
        self,
        task_id: str,
        session_id: str,
        phase: str | SessionPhase,
        **fields: Any,
    ) -> dict[str, Any]:
        ph = phase.value if isinstance(phase, SessionPhase) else phase
        cp = Checkpoint(
            task_id=task_id,
            session_id=session_id,
            phase=ph,
            head=fields.get("head", ""),
            changed_files=list(fields.get("changed_files") or []),
            test_state=fields.get("test_state", ""),
            warnings=list(fields.get("warnings") or []),
            blocker_state=fields.get("blocker_state", ""),
            next_action=fields.get("next_action", ""),
            rollback_point=fields.get("rollback_point", ""),
        )
        self.store.add_checkpoint(cp)
        sess = self.store.get_session(session_id) or {"session_id": session_id}
        sess["phase"] = ph
        sess["last_checkpoint"] = cp.timestamp
        self.store.put_session(sess)
        return cp.to_dict()

    # ---- launch (gated) ----
    def launch(
        self,
        item_id: str,
        *,
        adapter_name: str = "mock",
        knowledge_context: str = "",
        write_enabled: bool = False,
        poll_until_done: bool = True,
        max_polls: int = 5,
    ) -> OrchestratorResult:
        if not self.settings.orchestrator_enabled:
            return OrchestratorResult(
                ok=False,
                verdict=Verdict.BLOCKED.value,
                item_id=item_id,
                details={"error": "orchestrator_disabled"},
            )

        action = "launch_write_agent" if write_enabled else "launch_readonly_agent"
        ok, reason = permission_for_action(action, self.settings)
        if not ok:
            return OrchestratorResult(
                ok=False,
                verdict=Verdict.BLOCKED.value,
                item_id=item_id,
                details={"error": reason},
            )

        if adapter_name not in self.settings.allowed_agent_adapters:
            return OrchestratorResult(
                ok=False,
                verdict=Verdict.BLOCKED.value,
                item_id=item_id,
                details={"error": f"adapter_not_allowed:{adapter_name}"},
            )

        if self.store.active_session_count() >= self.settings.max_active_sessions:
            return OrchestratorResult(
                ok=False,
                verdict=Verdict.BLOCKED.value,
                item_id=item_id,
                details={"error": "max_active_sessions"},
            )

        item = self.store.get_item(item_id)
        if not item:
            return OrchestratorResult(
                ok=False,
                verdict=Verdict.FAILED.value,
                details={"error": "item_not_found"},
            )

        if item.approval_requirement:
            return OrchestratorResult(
                ok=False,
                verdict=Verdict.BLOCKED.value,
                item_id=item_id,
                details={"error": "awaiting_approval", "required_approvals": ["human"]},
            )

        ready = check_repository_readiness(
            self.root,
            self.settings,
            active_writer=False,
        )
        if write_enabled and not ready.ok_for_write_launch:
            if ready.state in ("unsafe", "blocked"):
                return OrchestratorResult(
                    ok=False,
                    verdict=Verdict.BLOCKED.value,
                    item_id=item_id,
                    details={"error": "readiness_blocked", "readiness": ready.to_dict()},
                )

        # mark selected → in_progress
        if item.status in (ItemStatus.PROPOSED.value, ItemStatus.READY.value):
            try:
                self.store.set_status(item_id, ItemStatus.SELECTED)
                self.store.set_status(item_id, ItemStatus.IN_PROGRESS)
            except ValueError as exc:
                return OrchestratorResult(
                    ok=False,
                    verdict=Verdict.FAILED.value,
                    item_id=item_id,
                    details={"error": str(exc)},
                )

        task = EngineeringTask(
            task_id=new_id("task"),
            item_id=item.item_id,
            objective=item.title,
            scope=list(item.acceptance_criteria),
            out_of_scope=list(item.out_of_scope),
            starting_commit=ready.head,
            branch=ready.branch,
            repository_root=str(self.root),
            validation_plan=list(item.required_validations) or [
                "engineering_tests", "secret_scan", "git_diff_check",
                "trading_guardian_isolation",
            ],
        )
        self.store.save_task(task)
        prompt = build_engineering_prompt(
            item, task, knowledge_context=knowledge_context
        )
        self.checkpoint(
            task.task_id, "prelaunch", SessionPhase.INTAKE,
            head=ready.head, next_action="launch_agent",
        )

        adapter = get_adapter(adapter_name)
        req = LaunchRequest(
            prompt=prompt.body,
            working_directory=str(self.root),
            timeout_sec=self.settings.session_timeout_sec,
        )
        try:
            started = adapter.start(req, allowed_root=str(self.root))
        except Exception as exc:
            self.store.set_status(item_id, ItemStatus.FAILED)
            return OrchestratorResult(
                ok=False,
                verdict=Verdict.FAILED.value,
                item_id=item_id,
                task_id=task.task_id,
                details={"error": f"launch_failed:{exc}"},
            )

        session = {
            "session_id": started.session_id,
            "status": started.status,
            "item_id": item_id,
            "task_id": task.task_id,
            "adapter": adapter_name,
            "started_at": started.started_at or time.time(),
            "branch": ready.branch,
            "head": ready.head,
            "pid": started.process_id,
            "write_enabled": write_enabled,
        }
        self.store.put_session(session)
        self.monitor.heartbeat(started.session_id, phase=SessionPhase.IMPLEMENTATION_PLAN.value)
        self.checkpoint(
            task.task_id, started.session_id, SessionPhase.IMPLEMENTATION_PLAN,
            head=ready.head, next_action="monitor",
        )

        last = started
        if poll_until_done:
            for _ in range(max_polls):
                last = adapter.poll(started.session_id)
                self.monitor.heartbeat(
                    started.session_id,
                    status=last.status,
                    last_output=last.stdout_tail,
                    last_output_time=time.time(),
                )
                snap = self.monitor.snapshot(
                    started.session_id,
                    expected_branch=ready.branch,
                    current_branch=ready.branch,
                    current_head=ready.head,
                    process_alive=last.status not in (
                        SessionStatus.CRASHED.value, SessionStatus.FAILED.value,
                    ),
                    output_text=last.stdout_tail + "\n" + last.stderr_tail,
                )
                stop = self.stop_policy.evaluate(detections=snap.detections)
                if stop.should_stop:
                    adapter.request_stop(started.session_id, force=stop.force)
                    if stop.force:
                        self.stop_policy.record_forced_termination(
                            started.session_id, stop.reason
                        )
                    self.store.set_status(item_id, ItemStatus.STOPPED)
                    self.store.put_session({
                        **session, "status": SessionStatus.STOPPED.value,
                        "stop_reason": stop.reason,
                    })
                    return OrchestratorResult(
                        ok=False,
                        verdict=Verdict.BLOCKED.value,
                        item_id=item_id,
                        task_id=task.task_id,
                        session_id=started.session_id,
                        details={"stop": stop.to_dict(), "monitor": snap.to_dict()},
                    )
                if last.status in (
                    SessionStatus.COMPLETED.value,
                    SessionStatus.FAILED.value,
                    SessionStatus.CRASHED.value,
                    SessionStatus.TIMED_OUT.value,
                    SessionStatus.USAGE_LIMIT.value,
                    SessionStatus.STOPPED.value,
                ):
                    break

        # validation phase
        try:
            self.store.set_status(item_id, ItemStatus.VALIDATING)
        except ValueError:
            pass
        self.checkpoint(
            task.task_id, started.session_id, SessionPhase.FOCUSED_TESTS,
            head=ready.head, next_action="validate",
        )
        vc = ValidationCoordinator(self.root)
        # For mock pilot success path, use internal checks that don't need full suite
        plan_names = [
            n for n in task.validation_plan
            if n != "engineering_tests" or adapter_name != "mock"
        ]
        if adapter_name == "mock":
            plan_names = [
                "secret_scan", "trading_guardian_isolation", "permission_tests",
            ]
        vresult = vc.run_plan(plan_names or ["secret_scan", "trading_guardian_isolation"])

        if last.status != SessionStatus.COMPLETED.value:
            try:
                self.store.set_status(item_id, ItemStatus.FAILED)
            except ValueError:
                self.store.set_status(item_id, ItemStatus.PARTIAL)
            handoff = self._write_handoff(
                item, task, started.session_id, ready,
                verdict=Verdict.FAILED.value,
                tests=str(vresult.to_dict()),
                failures=[last.error or last.status],
                next_action="inspect failure and decide retry",
            )
            return OrchestratorResult(
                ok=False,
                verdict=Verdict.FAILED.value,
                item_id=item_id,
                task_id=task.task_id,
                session_id=started.session_id,
                details={
                    "session": last.to_dict(),
                    "validation": vresult.to_dict(),
                    "handoff": handoff,
                },
            )

        if not vresult.all_required_passed:
            try:
                self.store.set_status(item_id, ItemStatus.REPAIR_REQUIRED)
            except ValueError:
                pass
            handoff = self._write_handoff(
                item, task, started.session_id, ready,
                verdict=Verdict.VALIDATION_PENDING.value,
                tests=str(vresult.to_dict()),
                failures=["required_validation_failed"],
                next_action="repair or re-validate",
            )
            return OrchestratorResult(
                ok=False,
                verdict=Verdict.VALIDATION_PENDING.value,
                item_id=item_id,
                task_id=task.task_id,
                session_id=started.session_id,
                details={"validation": vresult.to_dict(), "handoff": handoff},
            )

        try:
            self.store.set_status(item_id, ItemStatus.COMPLETED)
        except ValueError:
            pass
        self.store.put_session({
            **session,
            "status": SessionStatus.COMPLETED.value,
        })
        self.checkpoint(
            task.task_id, started.session_id, SessionPhase.HANDOFF_UPDATED,
            head=ready.head, test_state="passed", next_action="stop",
        )
        handoff = self._write_handoff(
            item, task, started.session_id, ready,
            verdict=Verdict.PILOT_READY.value,
            tests="required validations passed",
            failures=[],
            next_action="review pilot evidence; do not auto-merge",
            completed=["orchestrated pilot session completed"],
        )
        return OrchestratorResult(
            ok=True,
            verdict=Verdict.PILOT_READY.value,
            item_id=item_id,
            task_id=task.task_id,
            session_id=started.session_id,
            details={
                "session": last.to_dict(),
                "validation": vresult.to_dict(),
                "prompt_version": prompt.prompt_version,
                "task_fingerprint": task.fingerprint(),
                "handoff": handoff,
                "trading_guardian": trading_guardian_isolation_report(),
            },
        )

    def stop(self, session_id: str, *, force: bool = False) -> dict[str, Any]:
        sess = self.store.get_session(session_id)
        if not sess:
            return {"error": "session_not_found"}
        adapter_name = sess.get("adapter") or "mock"
        try:
            adapter = get_adapter(adapter_name)
        except Exception:
            adapter = get_adapter("mock")
        # If session was started in another process, still mark stopped
        result = adapter.request_stop(session_id, force=force)
        if force:
            self.stop_policy.record_forced_termination(session_id, "operator_force")
        sess["status"] = SessionStatus.STOPPED.value
        self.store.put_session(sess)
        item_id = sess.get("item_id")
        if item_id:
            try:
                self.store.set_status(item_id, ItemStatus.STOPPED)
            except Exception:
                pass
        return {"session": result.to_dict(), "forced": force}

    def validate_item(self, item_id: str) -> dict[str, Any]:
        item = self.store.get_item(item_id)
        if not item:
            return {"error": "not_found"}
        plan = item.required_validations or [
            "secret_scan", "trading_guardian_isolation", "permission_tests",
        ]
        vc = ValidationCoordinator(self.root)
        return vc.run_plan(plan).to_dict()

    def verify_commit_head(self, **kwargs: Any) -> dict[str, Any]:
        return verify_commit(self.root, **kwargs).to_dict()

    def verify_push(self, **kwargs: Any) -> dict[str, Any]:
        return pre_push_check(self.root, self.settings, **kwargs).to_dict()

    def history(self, limit: int = 20) -> list[dict[str, Any]]:
        path = self.store.history_path
        if not path.exists():
            return []
        lines = path.read_text(encoding="utf-8").splitlines()[-limit:]
        import json
        out = []
        for ln in lines:
            try:
                out.append(json.loads(ln))
            except Exception:
                continue
        return out

    def _write_handoff(
        self,
        item: EngineeringBacklogItem,
        task: EngineeringTask,
        session_id: str,
        ready: Any,
        *,
        verdict: str,
        tests: str,
        failures: list[str],
        next_action: str,
        completed: list[str] | None = None,
    ) -> dict[str, str]:
        payload = HandoffPayload(
            repository=item.repository_id,
            branch=getattr(ready, "branch", "") or task.branch,
            head=getattr(ready, "head", "") or task.starting_commit,
            remote_state="unknown",
            active_milestone=item.milestone_id,
            completed_work=completed or [],
            changed_files=[],
            commits=[],
            tests=tests,
            failures=failures,
            blockers=list(item.unresolved_blockers),
            rollback=item.rollback_requirement,
            disable_controls=disable_procedure(),
            remaining_risks=["pilot only — not production"],
            exact_next_action=next_action,
            agent_session_active=False,
            user_approval_required=item.approval_requirement,
            verdict=verdict,
        )
        paths = self.handoff_mgr.write(payload)
        self.store.append_history({
            "event": "handoff",
            "item_id": item.item_id,
            "session_id": session_id,
            "verdict": verdict,
        })
        return paths


def default_orchestrator(**kwargs: Any) -> EngineeringOrchestrator:
    return EngineeringOrchestrator(**kwargs)
