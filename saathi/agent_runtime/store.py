"""M10 durable run store — data/agent_runtime.db.

Persists orchestration runs, agent runs/steps, tasks + dependencies,
delegations, tool requests, approvals, verifications, reviews, retries,
budgets, events, checkpoints, failures, outcomes, agent messages, artifacts.
Every state transition is validated + timestamped + attributable + recoverable.
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Optional

from saathi.agent_runtime.models import RunState, validate_transition

ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH = ROOT / "data" / "agent_runtime.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS orchestration_run(
  id TEXT PRIMARY KEY, objective TEXT, strategy TEXT, state TEXT,
  actor TEXT, project_id TEXT DEFAULT '', conversation_id TEXT DEFAULT '',
  budget TEXT DEFAULT '{}', created_at REAL, updated_at REAL,
  final_outcome TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS agent_run(
  id TEXT PRIMARY KEY, run_id TEXT, agent TEXT, task_id TEXT DEFAULT '',
  state TEXT, created_at REAL, finished_at REAL DEFAULT 0);
CREATE TABLE IF NOT EXISTS agent_step(
  id TEXT PRIMARY KEY, agent_run_id TEXT, kind TEXT, detail TEXT,
  tokens INTEGER DEFAULT 0, created_at REAL);
CREATE TABLE IF NOT EXISTS task(
  id TEXT PRIMARY KEY, run_id TEXT, objective TEXT, agent TEXT,
  status TEXT, risk_class INTEGER, requires_approval INTEGER,
  spec TEXT DEFAULT '{}', result TEXT DEFAULT '', created_at REAL, updated_at REAL);
CREATE TABLE IF NOT EXISTS task_dependency(
  id TEXT PRIMARY KEY, task_id TEXT, depends_on TEXT);
CREATE TABLE IF NOT EXISTS delegation(
  id TEXT PRIMARY KEY, run_id TEXT, parent_agent TEXT, child_agent TEXT,
  objective TEXT, depth INTEGER, scopes TEXT DEFAULT '[]', created_at REAL);
CREATE TABLE IF NOT EXISTS tool_request(
  id TEXT PRIMARY KEY, run_id TEXT, agent TEXT, tool TEXT, intent_id TEXT DEFAULT '',
  risk INTEGER, status TEXT, result TEXT DEFAULT '', created_at REAL);
CREATE TABLE IF NOT EXISTS approval_request(
  id TEXT PRIMARY KEY, run_id TEXT, task_id TEXT DEFAULT '', agent TEXT,
  action TEXT, risk INTEGER, status TEXT DEFAULT 'pending',
  resolved_by TEXT DEFAULT '', expires_at REAL, created_at REAL, resolved_at REAL DEFAULT 0);
CREATE TABLE IF NOT EXISTS verification(
  id TEXT PRIMARY KEY, run_id TEXT, task_id TEXT, strategy TEXT,
  passed INTEGER, detail TEXT DEFAULT '', created_at REAL);
CREATE TABLE IF NOT EXISTS review(
  id TEXT PRIMARY KEY, run_id TEXT, task_id TEXT, reviewer TEXT,
  verdict TEXT, findings TEXT DEFAULT '[]', created_at REAL);
CREATE TABLE IF NOT EXISTS retry(
  id TEXT PRIMARY KEY, run_id TEXT, task_id TEXT, attempt INTEGER,
  fingerprint TEXT, reason TEXT, created_at REAL);
CREATE TABLE IF NOT EXISTS run_event(
  id TEXT PRIMARY KEY, run_id TEXT, name TEXT, payload TEXT DEFAULT '{}', created_at REAL);
CREATE TABLE IF NOT EXISTS run_checkpoint(
  id TEXT PRIMARY KEY, run_id TEXT, label TEXT, snapshot TEXT, created_at REAL);
CREATE TABLE IF NOT EXISTS failure(
  id TEXT PRIMARY KEY, run_id TEXT, task_id TEXT DEFAULT '', error TEXT,
  fingerprint TEXT, created_at REAL);
CREATE TABLE IF NOT EXISTS artifact(
  id TEXT PRIMARY KEY, run_id TEXT, task_id TEXT DEFAULT '', kind TEXT,
  name TEXT, content TEXT DEFAULT '', created_at REAL);
CREATE TABLE IF NOT EXISTS agent_message(
  id TEXT PRIMARY KEY, run_id TEXT, sender TEXT, receiver TEXT,
  msg_type TEXT, body TEXT DEFAULT '{}', created_at REAL);
CREATE INDEX IF NOT EXISTS idx_ev_run ON run_event(run_id, created_at);
CREATE INDEX IF NOT EXISTS idx_task_run ON task(run_id);
CREATE INDEX IF NOT EXISTS idx_ar_run ON agent_run(run_id);
"""


def _now() -> float:
    return time.time()


def _id() -> str:
    return uuid.uuid4().hex


class RunStore:
    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path) if db_path else DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(_SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(str(self.db_path))
        c.row_factory = sqlite3.Row
        return c

    # ── runs ──────────────────────────────────────────────────────────────
    def create_run(self, *, objective: str, strategy: str, actor: str,
                   project_id: str = "", conversation_id: str = "",
                   budget: dict | None = None) -> str:
        rid = _id()
        now = _now()
        with self._conn() as c:
            c.execute("INSERT INTO orchestration_run(id,objective,strategy,state,"
                      "actor,project_id,conversation_id,budget,created_at,updated_at)"
                      " VALUES(?,?,?,?,?,?,?,?,?,?)",
                      (rid, objective, strategy, RunState.CREATED.value, actor,
                       project_id, conversation_id, json.dumps(budget or {}), now, now))
        self.event(rid, "run.created", {"objective": objective[:120],
                                        "strategy": strategy})
        return rid

    def get_run(self, rid: str) -> Optional[dict]:
        with self._conn() as c:
            row = c.execute("SELECT * FROM orchestration_run WHERE id=?", (rid,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["budget"] = json.loads(d.get("budget") or "{}")
        return d

    def transition(self, rid: str, dst: RunState, *, actor: str = "system") -> None:
        run = self.get_run(rid)
        if not run:
            raise KeyError(rid)
        src = RunState(run["state"])
        validate_transition(src, dst)   # raises IllegalTransition
        with self._conn() as c:
            c.execute("UPDATE orchestration_run SET state=?, updated_at=? WHERE id=?",
                      (dst.value, _now(), rid))
        self.event(rid, "run.state", {"from": src.value, "to": dst.value,
                                      "actor": actor})

    def set_outcome(self, rid: str, outcome: dict) -> None:
        with self._conn() as c:
            c.execute("UPDATE orchestration_run SET final_outcome=?, updated_at=? "
                      "WHERE id=?", (json.dumps(outcome), _now(), rid))

    def list_runs(self, *, limit: int = 50, conversation_id: str | None = None) -> list[dict]:
        where, args = "", []
        if conversation_id:
            where = " WHERE conversation_id=?"
            args.append(conversation_id)
        args.append(limit)
        with self._conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT id,objective,strategy,state,actor,conversation_id,created_at "
                f"FROM orchestration_run{where} ORDER BY created_at DESC LIMIT ?",
                args).fetchall()]

    # ── tasks ─────────────────────────────────────────────────────────────
    def add_task(self, rid: str, task) -> None:
        with self._conn() as c:
            c.execute("INSERT INTO task(id,run_id,objective,agent,status,risk_class,"
                      "requires_approval,spec,created_at,updated_at) VALUES"
                      "(?,?,?,?,?,?,?,?,?,?)",
                      (task.task_id, rid, task.objective, task.agent, task.status,
                       int(task.risk_class), 1 if task.requires_approval else 0,
                       json.dumps(task.to_dict()), _now(), _now()))
            for d in task.dependencies:
                c.execute("INSERT INTO task_dependency VALUES(?,?,?)",
                          (_id(), task.task_id, d))

    def update_task(self, task_id: str, *, status: str = None, result: str = None):
        sets, args = ["updated_at=?"], [_now()]
        if status is not None:
            sets.append("status=?"); args.append(status)
        if result is not None:
            sets.append("result=?"); args.append(result)
        args.append(task_id)
        with self._conn() as c:
            c.execute(f"UPDATE task SET {','.join(sets)} WHERE id=?", args)

    def list_tasks(self, rid: str) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM task WHERE run_id=? ORDER BY created_at",
                             (rid,)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["spec"] = json.loads(d.get("spec") or "{}")
            out.append(d)
        return out

    # ── delegations / tools / approvals ───────────────────────────────────
    def add_delegation(self, rid: str, *, parent: str, child: str, objective: str,
                       depth: int, scopes: list[str]) -> str:
        did = _id()
        with self._conn() as c:
            c.execute("INSERT INTO delegation VALUES(?,?,?,?,?,?,?,?)",
                      (did, rid, parent, child, objective, depth,
                       json.dumps(scopes), _now()))
        self.event(rid, "delegation.created", {"parent": parent, "child": child})
        return did

    def delegations(self, rid: str) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT * FROM delegation WHERE run_id=? ORDER BY created_at",
                (rid,)).fetchall()]

    def add_tool_request(self, rid: str, *, agent: str, tool: str, risk: int,
                         status: str, intent_id: str = "", result: str = "") -> str:
        tid = _id()
        with self._conn() as c:
            c.execute("INSERT INTO tool_request VALUES(?,?,?,?,?,?,?,?,?)",
                      (tid, rid, agent, tool, intent_id, risk, status, result, _now()))
        self.event(rid, "tool.requested", {"agent": agent, "tool": tool, "status": status})
        return tid

    def tool_requests(self, rid: str) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT * FROM tool_request WHERE run_id=?", (rid,)).fetchall()]

    def add_approval(self, rid: str, *, agent: str, action: str, risk: int,
                     task_id: str = "", ttl_sec: float = 3600) -> str:
        aid = _id()
        now = _now()
        with self._conn() as c:
            c.execute("INSERT INTO approval_request(id,run_id,task_id,agent,action,"
                      "risk,status,expires_at,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                      (aid, rid, task_id, agent, action, risk, "pending",
                       now + ttl_sec, now))
        self.event(rid, "approval.requested", {"agent": agent, "action": action[:80]})
        return aid

    def get_approval(self, aid: str) -> Optional[dict]:
        with self._conn() as c:
            row = c.execute("SELECT * FROM approval_request WHERE id=?", (aid,)).fetchone()
        return dict(row) if row else None

    def resolve_approval(self, aid: str, *, approved: bool, actor: str) -> dict:
        appr = self.get_approval(aid)
        if not appr:
            raise KeyError(aid)
        if appr["status"] != "pending":
            return appr  # idempotent
        if _now() > appr["expires_at"]:
            status = "expired"
        else:
            status = "approved" if approved else "denied"
        with self._conn() as c:
            c.execute("UPDATE approval_request SET status=?, resolved_by=?, "
                      "resolved_at=? WHERE id=?", (status, actor, _now(), aid))
        self.event(appr["run_id"], "approval.resolved",
                   {"id": aid, "status": status, "actor": actor})
        return self.get_approval(aid)

    def pending_approvals(self, rid: str) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT * FROM approval_request WHERE run_id=? AND status='pending'",
                (rid,)).fetchall()]

    # ── verification / review / retry / failure ───────────────────────────
    def add_verification(self, rid: str, task_id: str, strategy: str, passed: bool,
                         detail: str = "") -> None:
        with self._conn() as c:
            c.execute("INSERT INTO verification VALUES(?,?,?,?,?,?,?)",
                      (_id(), rid, task_id, strategy, 1 if passed else 0, detail, _now()))
        self.event(rid, "verification.passed" if passed else "verification.failed",
                   {"task": task_id, "strategy": strategy})

    def verifications(self, rid: str) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT * FROM verification WHERE run_id=?", (rid,)).fetchall()]

    def add_review(self, rid: str, task_id: str, reviewer: str, verdict: str,
                   findings: list) -> None:
        with self._conn() as c:
            c.execute("INSERT INTO review VALUES(?,?,?,?,?,?,?)",
                      (_id(), rid, task_id, reviewer, verdict, json.dumps(findings), _now()))
        self.event(rid, "review.completed", {"task": task_id, "verdict": verdict})

    def add_retry(self, rid: str, task_id: str, attempt: int, fingerprint: str,
                  reason: str) -> None:
        with self._conn() as c:
            c.execute("INSERT INTO retry VALUES(?,?,?,?,?,?,?)",
                      (_id(), rid, task_id, attempt, fingerprint, reason, _now()))

    def add_failure(self, rid: str, error: str, fingerprint: str,
                    task_id: str = "") -> None:
        with self._conn() as c:
            c.execute("INSERT INTO failure VALUES(?,?,?,?,?,?)",
                      (_id(), rid, task_id, error[:500], fingerprint, _now()))
        self.event(rid, "task.failed", {"task": task_id})

    # ── artifacts / messages / steps ──────────────────────────────────────
    def add_artifact(self, rid: str, *, kind: str, name: str, content: str = "",
                     task_id: str = "") -> str:
        aid = _id()
        with self._conn() as c:
            c.execute("INSERT INTO artifact VALUES(?,?,?,?,?,?,?)",
                      (aid, rid, task_id, kind, name, content, _now()))
        return aid

    def artifacts(self, rid: str) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT * FROM artifact WHERE run_id=?", (rid,)).fetchall()]

    def add_message(self, rid: str, *, sender: str, receiver: str, msg_type: str,
                    body: dict) -> None:
        with self._conn() as c:
            c.execute("INSERT INTO agent_message VALUES(?,?,?,?,?,?,?)",
                      (_id(), rid, sender, receiver, msg_type, json.dumps(body), _now()))

    def messages(self, rid: str) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM agent_message WHERE run_id=? "
                             "ORDER BY created_at", (rid,)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["body"] = json.loads(d.get("body") or "{}")
            out.append(d)
        return out

    def add_agent_run(self, rid: str, agent: str, task_id: str = "") -> str:
        arid = _id()
        with self._conn() as c:
            c.execute("INSERT INTO agent_run(id,run_id,agent,task_id,state,created_at)"
                      " VALUES(?,?,?,?,?,?)", (arid, rid, agent, task_id, "running", _now()))
        self.event(rid, "agent.started", {"agent": agent})
        return arid

    def finish_agent_run(self, arid: str, state: str) -> None:
        with self._conn() as c:
            c.execute("UPDATE agent_run SET state=?, finished_at=? WHERE id=?",
                      (state, _now(), arid))

    # ── events / checkpoints ──────────────────────────────────────────────
    def event(self, rid: str, name: str, payload: dict | None = None) -> None:
        with self._conn() as c:
            c.execute("INSERT INTO run_event VALUES(?,?,?,?,?)",
                      (_id(), rid, name, json.dumps(payload or {}), _now()))
        # mirror to the fabric event bus (best-effort; never corrupts run state)
        try:
            from saathi.events import bus
            bus.publish_sync(f"agentrun.{name}", {"run_id": rid, **(payload or {})})
        except Exception:
            pass

    def events(self, rid: str, *, limit: int = 500, offset: int = 0) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM run_event WHERE run_id=? "
                             "ORDER BY created_at LIMIT ? OFFSET ?",
                             (rid, limit, offset)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["payload"] = json.loads(d.get("payload") or "{}")
            out.append(d)
        return out

    def checkpoint(self, rid: str, label: str = "") -> str:
        snap = json.dumps({"run": self.get_run(rid), "tasks": self.list_tasks(rid)},
                          default=str)
        kid = _id()
        with self._conn() as c:
            c.execute("INSERT INTO run_checkpoint VALUES(?,?,?,?,?)",
                      (kid, rid, label, snap, _now()))
        return kid

    def latest_checkpoint(self, rid: str) -> Optional[dict]:
        with self._conn() as c:
            row = c.execute("SELECT * FROM run_checkpoint WHERE run_id=? "
                            "ORDER BY created_at DESC LIMIT 1", (rid,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["snapshot"] = json.loads(d["snapshot"])
        return d

    def metrics(self, rid: str) -> dict:
        with self._conn() as c:
            tasks = c.execute("SELECT status, COUNT(*) n FROM task WHERE run_id=? "
                              "GROUP BY status", (rid,)).fetchall()
            ev = c.execute("SELECT COUNT(*) n FROM run_event WHERE run_id=?",
                           (rid,)).fetchone()["n"]
            tools = c.execute("SELECT COUNT(*) n FROM tool_request WHERE run_id=?",
                              (rid,)).fetchone()["n"]
            retries = c.execute("SELECT COUNT(*) n FROM retry WHERE run_id=?",
                                (rid,)).fetchone()["n"]
            deleg = c.execute("SELECT COUNT(*) n FROM delegation WHERE run_id=?",
                              (rid,)).fetchone()["n"]
        return {"tasks": {r["status"]: r["n"] for r in tasks}, "events": ev,
                "tool_calls": tools, "retries": retries, "delegations": deleg}
