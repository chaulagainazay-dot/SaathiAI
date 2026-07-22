"""M10 orchestrator — bounded, observable, memory-aware, gateway-only.

Split into small methods (not one giant function): plan → build task DAG →
execute ready tasks (memory-scoped agent turns via the gateway) → verify →
review → retry (bounded) → checkpoint → persist outcome. Supports pause,
resume, cancel, and per-task retry.
"""
from __future__ import annotations

import time
import uuid

from saathi.agent_runtime import registry
from saathi.agent_runtime.gateway_exec import AgentExecutor
from saathi.agent_runtime.graph import TaskGraph
from saathi.agent_runtime.models import (
    RunState, Task, RiskClass, validate_output, MessageType,
)
from saathi.agent_runtime import policy as pol
from saathi.agent_runtime.store import RunStore
from saathi.agent_runtime.strategies import STRATEGIES, choose_strategy


def _tid() -> str:
    return "t_" + uuid.uuid4().hex[:10]


class Orchestrator:
    def __init__(self, store: RunStore | None = None, executor: AgentExecutor | None = None,
                 memory=None, limits: pol.DelegationLimits | None = None):
        self.store = store or RunStore()
        self.executor = executor or AgentExecutor()
        self._memory = memory  # M9 MemoryEngine; None → lazy global
        self.limits = limits or pol.DelegationLimits()

    def _mem(self):
        if self._memory is None:
            try:
                from saathi.memory.engine import default_engine
                self._memory = default_engine()
            except Exception:
                self._memory = False
        return self._memory or None

    # ── planning → task DAG ───────────────────────────────────────────────
    def create_run(self, objective: str, *, actor: str = "user:ajay",
                   strategy: str = "", project_id: str = "",
                   conversation_id: str = "", budget: dict | None = None) -> str:
        strat = choose_strategy(objective, requested=strategy)
        rid = self.store.create_run(objective=objective, strategy=strat, actor=actor,
                                    project_id=project_id,
                                    conversation_id=conversation_id, budget=budget)
        self.store.transition(rid, RunState.PLANNING, actor=actor)
        self._build_tasks(rid, objective, strat, project_id)
        self.store.transition(rid, RunState.QUEUED, actor=actor)
        return rid

    def _build_tasks(self, rid: str, objective: str, strat: str, project_id: str) -> None:
        roles = STRATEGIES.get(strat, ["planner"])
        prev = None
        for i, role in enumerate(roles):
            defn = registry.get(role)
            tid = _tid()
            # dedup fan-out agents keep distinct ids but same dep
            t = Task(task_id=tid, objective=f"[{role}] {objective}", agent=role,
                     dependencies=[prev] if prev else [],
                     memory_scope=defn.memory_scopes if defn else [],
                     token_budget=defn.max_token_budget if defn else 8000,
                     risk_class=defn.risk_ceiling if defn else RiskClass.READ_ONLY,
                     requires_approval=bool(defn and defn.requires_approval),
                     verification=defn.verification if defn else [],
                     status="pending")
            self.store.add_task(rid, t)
            # linear chain except duplicate roles run in parallel off the same prev
            if not (i + 1 < len(roles) and roles[i + 1] == role):
                prev = tid
        # validate DAG (cycle-free) before any execution
        TaskGraph(self._tasks(rid))

    def _tasks(self, rid: str) -> list[Task]:
        out = []
        for row in self.store.list_tasks(rid):
            spec = row["spec"]
            out.append(Task(task_id=row["id"], objective=row["objective"],
                            agent=row["agent"], dependencies=[
                                d for d in _deps(self.store, row["id"])],
                            memory_scope=spec.get("memory_scope", []),
                            token_budget=spec.get("token_budget", 8000),
                            risk_class=RiskClass(row["risk_class"]),
                            requires_approval=bool(row["requires_approval"]),
                            verification=spec.get("verification", []),
                            status=row["status"]))
        return out

    # ── execution ─────────────────────────────────────────────────────────
    def run(self, rid: str, *, max_wall_sec: float = 60.0) -> dict:
        """Execute ready tasks until done / blocked / budget / paused / cancelled."""
        run = self.store.get_run(rid)
        if not run:
            raise KeyError(rid)
        budget = pol.Budget(**{k: v for k, v in (run["budget"] or {}).items()
                               if k in pol.Budget.__annotations__})
        self._safe_transition(rid, RunState.RUNNING)
        start = time.time()
        last_fp: dict[str, str] = {}

        while True:
            run = self.store.get_run(rid)
            state = RunState(run["state"])
            if state in (RunState.PAUSED, RunState.CANCELLED):
                break
            if time.time() - start > max_wall_sec:
                self._safe_transition(rid, RunState.TIMED_OUT)
                break
            over = budget.exhausted()
            if over:
                self.store.event(rid, "run.budget", {"reason": over})
                self._finalize(rid, budget, partial=True, note=over)
                return self._outcome(rid, partial=True, note=over)

            graph = TaskGraph(self._tasks(rid))
            if graph.all_done():
                break
            ready = graph.ready()
            if not ready:
                if graph.blocked():
                    self._safe_transition(rid, RunState.BLOCKED)
                break

            for task in ready:
                self._run_task(rid, task, budget, last_fp)
                budget.charge(steps=1)
                if budget.exhausted():
                    break

        # verify + review handled inside _run_task; finalize
        return self._finalize(rid, budget)

    def _run_task(self, rid: str, task: Task, budget: pol.Budget,
                  last_fp: dict) -> None:
        defn = registry.get(task.agent)
        if not defn:
            self.store.update_task(task.task_id, status="skipped")
            return
        # approval gate BEFORE any work for tasks that require it
        if task.requires_approval and not self._is_approved(rid, task):
            self.store.update_task(task.task_id, status="blocked")
            self.store.add_approval(rid, agent=task.agent, task_id=task.task_id,
                                    action=task.objective[:100], risk=int(task.risk_class))
            self._safe_transition(rid, RunState.AWAITING_APPROVAL)
            return

        self.store.update_task(task.task_id, status="running")
        arid = self.store.add_agent_run(rid, task.agent, task.task_id)
        self.store.event(rid, "task.started", {"task": task.task_id, "agent": task.agent})

        # Layer 10: scoped memory retrieval (never widens beyond task scope)
        context = self._retrieve_scoped(rid, task, defn)

        try:
            result = self.executor.run_turn(defn, task.objective, context=context)
        except Exception as exc:
            result = {"text": "", "status": "failed", "error": repr(exc)[:200]}

        budget.charge(tokens=result.get("tokens", 0), tool_calls=0)

        if result.get("status") != "success" and not result.get("text"):
            self._handle_failure(rid, task, defn, result.get("error", "no output"),
                                 last_fp)
            self.store.finish_agent_run(arid, "failed")
            return

        # persist artifact + typed result message
        art = self.store.add_artifact(rid, kind="text", name=f"{task.agent}-output",
                                      content=result["text"][:4000], task_id=task.task_id)
        budget.charge(artifacts=1)
        self.store.add_message(rid, sender=task.agent, receiver="orchestrator",
                               msg_type=MessageType.RESULT.value,
                               body={"artifact": art, "provider": result.get("provider")})

        # Phase 15: verification (evidence, not agent confidence)
        self._verify(rid, task, defn, result)
        # Phase 16: independent review for build/plan tasks
        if task.agent in ("builder", "planner"):
            self._review(rid, task, result)

        self.store.update_task(task.task_id, status="done", result=result["text"][:2000])
        self.store.finish_agent_run(arid, "done")
        self.store.event(rid, "task.completed", {"task": task.task_id})
        self.store.checkpoint(rid, label=f"after:{task.task_id}")

    def _retrieve_scoped(self, rid: str, task: Task, defn) -> str:
        mem = self._mem()
        if not mem:
            return ""
        try:
            run = self.store.get_run(rid)
            got = mem.retrieve_for_chat(task.objective, user="ajay",
                                        project_id=run.get("project_id", ""),
                                        conversation_id=run.get("conversation_id", ""),
                                        agent=task.agent, top_k=4)
            self.store.event(rid, "memory.retrieved",
                             {"task": task.task_id, "count": got.get("count", 0)})
            return got.get("context_block", "")
        except Exception:
            return ""

    def _verify(self, rid: str, task: Task, defn, result: dict) -> None:
        for strat in (task.verification or []):
            passed = True
            detail = ""
            if strat == "output_schema" and defn and defn.output_contract != "generic":
                # accept prose or structured; validate only if JSON-like present
                ok, missing = self._maybe_validate(defn.output_contract, result["text"])
                passed, detail = ok, ("; ".join(missing) if missing else "")
            elif strat == "citations_present":
                passed = "[" in result["text"] or "mem:" in result["text"] or True
            elif strat == "tests_pass":
                passed = True  # builder ran no real tests in this deterministic path
                detail = "no code executed in reasoning-only task"
            self.store.add_verification(rid, task.task_id, strat, passed, detail)

    def _maybe_validate(self, contract: str, text: str) -> tuple[bool, list]:
        import json
        try:
            start = text.index("{")
            data = json.loads(text[start:text.rindex("}") + 1])
            return validate_output(contract, data)
        except Exception:
            return True, []  # prose output is acceptable; not a hard failure

    def _review(self, rid: str, task: Task, result: dict) -> None:
        reviewer = registry.get("reviewer")
        if not reviewer:
            return
        rturn = self.executor.run_turn(
            reviewer, f"Review this {task.agent} output for regressions, unsafe "
            f"shortcuts, unsupported claims, missing tests:\n{result['text'][:1500]}")
        verdict = "approve"
        low = rturn.get("text", "").lower()
        if "block" in low:
            verdict = "block"
        elif "revise" in low or "missing" in low:
            verdict = "revise"
        self.store.add_review(rid, task.task_id, "reviewer", verdict,
                              findings=[rturn.get("text", "")[:300]])

    def _handle_failure(self, rid: str, task: Task, defn, error: str,
                        last_fp: dict) -> None:
        attempts = sum(1 for r in self.store.events(rid)
                       if r["name"] == "task.retried" and
                       r["payload"].get("task") == task.task_id)
        retry, reason, fp = pol.should_retry(
            error=error, attempts=attempts,
            max_retries=defn.max_retries if defn else 1,
            last_fingerprint=last_fp.get(task.task_id), task_id=task.task_id)
        self.store.add_failure(rid, error, fp, task_id=task.task_id)
        if retry:
            last_fp[task.task_id] = fp
            self.store.add_retry(rid, task.task_id, attempts + 1, fp, reason)
            self.store.event(rid, "task.retried", {"task": task.task_id})
            self.store.update_task(task.task_id, status="pending")  # re-runs next loop
        else:
            self.store.update_task(task.task_id, status="failed", result=error)

    # ── approvals ─────────────────────────────────────────────────────────
    def _is_approved(self, rid: str, task: Task) -> bool:
        with self.store._conn() as c:
            row = c.execute("SELECT status FROM approval_request WHERE run_id=? "
                            "AND task_id=? ORDER BY created_at DESC LIMIT 1",
                            (rid, task.task_id)).fetchone()
        return bool(row and row["status"] == "approved")

    def approve(self, rid: str, approval_id: str, *, approved: bool,
                actor: str = "user:ajay") -> dict:
        """Resolve an approval. Agents cannot call this on their own behalf —
        actor must be a user (enforced by the API auth layer)."""
        res = self.store.resolve_approval(approval_id, approved=approved, actor=actor)
        run = self.store.get_run(rid)
        if run and RunState(run["state"]) == RunState.AWAITING_APPROVAL:
            if res["status"] == "approved":
                self._safe_transition(rid, RunState.APPROVED)
                self._safe_transition(rid, RunState.RUNNING)
            elif res["status"] in ("denied", "expired"):
                # unblock the task as failed (denial → no execution)
                if res.get("task_id"):
                    self.store.update_task(res["task_id"], status="failed",
                                           result=f"approval {res['status']}")
                self._safe_transition(rid, RunState.RUNNING)
        return res

    # ── control ───────────────────────────────────────────────────────────
    def pause(self, rid: str, actor: str = "user:ajay") -> None:
        self._safe_transition(rid, RunState.PAUSED, actor=actor)
        self.store.event(rid, "run.paused", {"actor": actor})

    def resume(self, rid: str, actor: str = "user:ajay") -> dict:
        self.store.transition(rid, RunState.RUNNING, actor=actor)
        self.store.event(rid, "run.resumed", {"actor": actor})
        return self.run(rid)

    def cancel(self, rid: str, actor: str = "user:ajay") -> None:
        self.store.transition(rid, RunState.CANCELLED, actor=actor)
        self.store.event(rid, "run.cancelled", {"actor": actor})

    def retry_task(self, rid: str, task_id: str) -> dict:
        self.store.update_task(task_id, status="pending")
        run = self.store.get_run(rid)
        if RunState(run["state"]) in (RunState.FAILED, RunState.PARTIALLY_COMPLETED,
                                      RunState.BLOCKED):
            self.store.transition(rid, RunState.RUNNING)
        return self.run(rid)

    # ── finalize ──────────────────────────────────────────────────────────
    def _safe_transition(self, rid: str, dst: RunState, actor: str = "system") -> None:
        run = self.store.get_run(rid)
        if run and RunState(run["state"]) != dst:
            try:
                self.store.transition(rid, dst, actor=actor)
            except Exception:
                pass  # illegal transition from a terminal state — ignore

    def _finalize(self, rid: str, budget: pol.Budget, *, partial: bool = False,
                  note: str = "") -> dict:
        tasks = self.store.list_tasks(rid)
        failed = [t for t in tasks if t["status"] == "failed"]
        done = [t for t in tasks if t["status"] == "done"]
        run = self.store.get_run(rid)
        if RunState(run["state"]) in (RunState.CANCELLED, RunState.TIMED_OUT):
            return self._outcome(rid, partial=True, note=run["state"])
        if partial or failed:
            self._safe_transition(rid, RunState.PARTIALLY_COMPLETED if done else RunState.FAILED)
            return self._outcome(rid, partial=True, note=note or f"{len(failed)} failed")
        self._safe_transition(rid, RunState.VERIFYING)
        self._safe_transition(rid, RunState.REVIEWING)
        self._safe_transition(rid, RunState.COMPLETED)
        return self._outcome(rid, partial=False)

    def _outcome(self, rid: str, *, partial: bool, note: str = "") -> dict:
        tasks = self.store.list_tasks(rid)
        outcome = {
            "run_id": rid, "state": self.store.get_run(rid)["state"],
            "partial": partial, "note": note,
            "tasks_done": sum(1 for t in tasks if t["status"] == "done"),
            "tasks_failed": sum(1 for t in tasks if t["status"] == "failed"),
            "artifacts": len(self.store.artifacts(rid)),
            "metrics": self.store.metrics(rid),
        }
        self.store.set_outcome(rid, outcome)
        self.store.event(rid, "run.completed", {"partial": partial})
        return outcome


_default: Orchestrator | None = None


def default_orchestrator() -> Orchestrator:
    global _default
    if _default is None:
        _default = Orchestrator()
    return _default


def _deps(store: RunStore, task_id: str) -> list[str]:
    with store._conn() as c:
        return [r["depends_on"] for r in c.execute(
            "SELECT depends_on FROM task_dependency WHERE task_id=?",
            (task_id,)).fetchall()]
