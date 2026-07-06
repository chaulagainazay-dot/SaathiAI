"""Workflows + Tasks — the missing hierarchy level.

    Mission → Department → Director → Workflow → Task

A Workflow is a reusable, named pipeline a Director runs (Instagram Growth, Daily
IELTS Lesson, SEO Sprint); Tasks are its steps. Reusable templates replace
hardcoded pipelines — the same "Daily IELTS Lesson" workflow drives every Mr. Yeti
episode, the same "Instagram Growth" drives every client's social. Everything is
scoped to a Mission so execution, evidence and learning all share its namespace.
"""
from __future__ import annotations

import sqlite3
import time
import uuid
from pathlib import Path

# reusable workflow templates keyed by director/role
TEMPLATES = {
    "social_media": {"name": "Instagram Growth",
                     "tasks": ["Research", "Script", "Design", "Review", "Publish", "Analytics"]},
    "content_studio": {"name": "Daily IELTS Lesson",
                       "tasks": ["Research", "Script", "Storyboard", "Voice", "Render", "Publish"]},
    "seo": {"name": "SEO Sprint",
            "tasks": ["Audit", "Keywords", "On-page fixes", "Content", "Backlinks", "Track"]},
    "sales": {"name": "Lead to Booking",
              "tasks": ["Lead intake", "Qualify", "Quotation", "Follow-up", "Close", "Onboard"]},
    "crm": {"name": "Client Retention",
            "tasks": ["Segment", "Reach out", "Offer", "Feedback", "Renew"]},
    "marketing": {"name": "Campaign", "tasks": ["Plan", "Create", "Launch", "Measure", "Optimise"]},
    "menu_planner": {"name": "Weekly Menu", "tasks": ["Forecast", "Order", "Prep", "Sell", "Waste review"]},
    "signal_engine": {"name": "Signal Cycle", "tasks": ["Research", "Setup", "Publish", "Track", "Report"]},
}
_GENERIC = {"name": "Workflow", "tasks": ["Plan", "Do", "Review", "Ship"]}

_STATUSES = ("todo", "doing", "done", "blocked")


class WorkflowStore:
    def __init__(self, db_path: str | None = None):
        self.db_path = Path(db_path) if db_path else (Path.home() / ".saathi" / "mission_workflows.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.execute("CREATE TABLE IF NOT EXISTS workflow(id TEXT PRIMARY KEY, mission_id TEXT, "
                      "department TEXT, director TEXT, name TEXT, template TEXT, status TEXT, created REAL)")
            c.execute("CREATE TABLE IF NOT EXISTS task(id TEXT PRIMARY KEY, workflow_id TEXT, mission_id TEXT, "
                      "title TEXT, status TEXT, ord INTEGER, director TEXT, notes TEXT, updated REAL)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_wf ON workflow(mission_id)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_tk ON task(workflow_id, ord)")

    def _conn(self):
        return sqlite3.connect(str(self.db_path))

    def create(self, mission_id: str, *, director: str = "", department: str = "",
               template: str = "", name: str = "") -> dict:
        tpl = TEMPLATES.get(template) or TEMPLATES.get(director) or _GENERIC
        wid = uuid.uuid4().hex[:16]
        wname = name or tpl["name"]
        with self._conn() as c:
            c.execute("INSERT INTO workflow VALUES(?,?,?,?,?,?,?,?)",
                      (wid, mission_id, department, director, wname, template or director, "active", time.time()))
            for i, t in enumerate(tpl["tasks"]):
                c.execute("INSERT INTO task VALUES(?,?,?,?,?,?,?,?,?)",
                          (uuid.uuid4().hex[:16], wid, mission_id, t, "todo", i, director, "", time.time()))
        return self.get(wid)

    def get(self, workflow_id: str) -> dict | None:
        with self._conn() as c:
            w = c.execute("SELECT id,mission_id,department,director,name,template,status,created "
                          "FROM workflow WHERE id=?", (workflow_id,)).fetchone()
            if not w:
                return None
            tasks = c.execute("SELECT id,title,status,ord,director,notes FROM task WHERE workflow_id=? "
                              "ORDER BY ord", (workflow_id,)).fetchall()
        keys = ["id", "mission_id", "department", "director", "name", "template", "status", "created"]
        d = dict(zip(keys, w))
        d["tasks"] = [dict(zip(["id", "title", "status", "ord", "director", "notes"], t)) for t in tasks]
        done = sum(1 for t in d["tasks"] if t["status"] == "done")
        d["progress"] = round(done / len(d["tasks"]), 2) if d["tasks"] else 0.0
        return d

    def list(self, mission_id: str) -> list[dict]:
        with self._conn() as c:
            ids = [r[0] for r in c.execute("SELECT id FROM workflow WHERE mission_id=? ORDER BY created",
                                           (mission_id,)).fetchall()]
        return [self.get(i) for i in ids]

    def set_task(self, task_id: str, status: str) -> bool:
        if status not in _STATUSES:
            return False
        with self._conn() as c:
            cur = c.execute("UPDATE task SET status=?, updated=? WHERE id=?",
                            (status, time.time(), task_id))
            return cur.rowcount > 0

    def open_tasks(self, mission_id: str, limit: int = 8) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("SELECT id,title,status,director FROM task WHERE mission_id=? AND status!='done' "
                             "ORDER BY (status='doing') DESC, ord LIMIT ?", (mission_id, limit)).fetchall()
        return [dict(zip(["id", "title", "status", "director"], r)) for r in rows]


# default department workflows stood up when a Mission enters execution
_EXECUTION_KIT = {
    "travel": [("marketing", "social_media"), ("seo", "seo"), ("sales", "sales")],
    "cafeteria": [("menu_planner", "menu_planner")],
    "education": [("content_studio", "content_studio"), ("seo", "seo")],
    "ai_studio": [("content_studio", "content_studio")],
    "crypto": [("signal_engine", "signal_engine")],
}


def provision_execution(mission_id: str, template_key: str, *, store=None) -> list[dict]:
    """When a Mission goes into execution, stand up its department workflows."""
    store = store or default_store()
    kit = _EXECUTION_KIT.get(template_key, [("marketing", "marketing")])
    return [store.create(mission_id, director=d, template=t) for d, t in kit]


_default = None
def default_store() -> WorkflowStore:
    global _default
    if _default is None:
        _default = WorkflowStore()
    return _default
