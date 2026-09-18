"""Organization mission store — durable record of org missions, delegation
steps, outputs, evidence references and an append-only event trail.

SQLite, one file (``SAATHI_ORG_DB`` or ``<repo>/data/organization.db``). This is
the organization layer's OWN record of what it orchestrated; it never mirrors or
mutates the M10 agent-runtime store or any trading/risk database.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parent.parent.parent

_SCHEMA = """
CREATE TABLE IF NOT EXISTS org_mission(
  id TEXT PRIMARY KEY, template TEXT NOT NULL, title TEXT NOT NULL,
  objective TEXT NOT NULL, status TEXT NOT NULL, created_by TEXT NOT NULL,
  source TEXT DEFAULT 'company_view', pacing_sec REAL DEFAULT 0,
  reason TEXT DEFAULT '', report TEXT DEFAULT '{}',
  created_at REAL, updated_at REAL, finished_at REAL DEFAULT 0);
CREATE TABLE IF NOT EXISTS org_step(
  id TEXT PRIMARY KEY, mission_id TEXT NOT NULL, parent_id TEXT DEFAULT '',
  seq INTEGER NOT NULL, role_id TEXT NOT NULL, objective TEXT NOT NULL,
  probe TEXT NOT NULL, status TEXT NOT NULL, reason TEXT DEFAULT '',
  output TEXT DEFAULT '{}', evidence TEXT DEFAULT '[]',
  started_at REAL DEFAULT 0, finished_at REAL DEFAULT 0);
CREATE TABLE IF NOT EXISTS org_event(
  id TEXT PRIMARY KEY, mission_id TEXT DEFAULT '', step_id TEXT DEFAULT '',
  role_id TEXT DEFAULT '', name TEXT NOT NULL, detail TEXT DEFAULT '{}',
  created_at REAL);
CREATE INDEX IF NOT EXISTS idx_org_step_mission ON org_step(mission_id, seq);
CREATE INDEX IF NOT EXISTS idx_org_step_role ON org_step(role_id, started_at);
CREATE INDEX IF NOT EXISTS idx_org_event_time ON org_event(created_at);
"""

MISSION_TERMINAL = frozenset({"COMPLETE", "COMPLETE_WITH_GAPS", "BLOCKED", "FAILED", "CANCELLED"})


def _now() -> float:
    return time.time()


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def default_db_path() -> Path:
    env = os.environ.get("SAATHI_ORG_DB")
    return Path(env) if env else ROOT / "data" / "organization.db"


class OrgStore:
    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path) if db_path else default_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(_SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(str(self.db_path), timeout=15)
        c.row_factory = sqlite3.Row
        return c

    # ── missions ──────────────────────────────────────────────────────────
    def create_mission(self, *, template: str, title: str, objective: str,
                       created_by: str, source: str, pacing_sec: float) -> str:
        mid = _id("om")
        now = _now()
        with self._conn() as c:
            c.execute(
                "INSERT INTO org_mission(id,template,title,objective,status,created_by,"
                "source,pacing_sec,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (mid, template, title, objective, "CREATED", created_by, source,
                 pacing_sec, now, now))
        return mid

    def set_mission(self, mid: str, *, status: str, reason: str = "",
                    report: dict | None = None) -> None:
        now = _now()
        fields = ["status=?", "updated_at=?", "reason=?"]
        args: list[Any] = [status, now, reason]
        if report is not None:
            fields.append("report=?")
            args.append(json.dumps(report, default=str))
        if status in MISSION_TERMINAL:
            fields.append("finished_at=?")
            args.append(now)
        args.append(mid)
        with self._conn() as c:
            c.execute(f"UPDATE org_mission SET {', '.join(fields)} WHERE id=?", args)

    def get_mission(self, mid: str) -> Optional[dict]:
        with self._conn() as c:
            row = c.execute("SELECT * FROM org_mission WHERE id=?", (mid,)).fetchone()
        return _mission(row) if row else None

    def list_missions(self, limit: int = 20) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM org_mission ORDER BY created_at DESC LIMIT ?",
                             (limit,)).fetchall()
        return [_mission(r) for r in rows]

    def active_missions(self) -> list[dict]:
        ph = ",".join("?" * len(MISSION_TERMINAL))
        with self._conn() as c:
            rows = c.execute(f"SELECT * FROM org_mission WHERE status NOT IN ({ph}) "
                             "ORDER BY created_at", tuple(MISSION_TERMINAL)).fetchall()
        return [_mission(r) for r in rows]

    # ── steps ─────────────────────────────────────────────────────────────
    def add_step(self, mid: str, *, parent_id: str, seq: int, role_id: str,
                 objective: str, probe: str) -> str:
        sid = _id("os")
        with self._conn() as c:
            c.execute(
                "INSERT INTO org_step(id,mission_id,parent_id,seq,role_id,objective,probe,status)"
                " VALUES(?,?,?,?,?,?,?,?)",
                (sid, mid, parent_id, seq, role_id, objective, probe, "ASSIGNED"))
        return sid

    def set_step(self, sid: str, *, status: str, reason: str = "",
                 output: dict | None = None, evidence: list | None = None,
                 started: bool = False, finished: bool = False) -> None:
        fields = ["status=?", "reason=?"]
        args: list[Any] = [status, reason]
        if output is not None:
            fields.append("output=?")
            args.append(json.dumps(output, default=str))
        if evidence is not None:
            fields.append("evidence=?")
            args.append(json.dumps(evidence, default=str))
        if started:
            fields.append("started_at=?")
            args.append(_now())
        if finished:
            fields.append("finished_at=?")
            args.append(_now())
        args.append(sid)
        with self._conn() as c:
            c.execute(f"UPDATE org_step SET {', '.join(fields)} WHERE id=?", args)

    def steps(self, mid: str) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM org_step WHERE mission_id=? ORDER BY seq",
                             (mid,)).fetchall()
        return [_step(r) for r in rows]

    def get_step(self, sid: str) -> Optional[dict]:
        with self._conn() as c:
            row = c.execute("SELECT * FROM org_step WHERE id=?", (sid,)).fetchone()
        return _step(row) if row else None

    def latest_step_per_role(self, since: float) -> dict[str, dict]:
        """Most recent step per role among steps that are active or finished
        after ``since`` (joined with the mission status)."""
        with self._conn() as c:
            rows = c.execute(
                "SELECT s.*, m.status AS mission_status, m.title AS mission_title "
                "FROM org_step s JOIN org_mission m ON m.id=s.mission_id "
                "WHERE s.finished_at=0 OR s.finished_at>=? "
                "ORDER BY s.started_at, s.seq", (since,)).fetchall()
        out: dict[str, dict] = {}
        for r in rows:
            d = _step(r)
            d["mission_status"] = r["mission_status"]
            d["mission_title"] = r["mission_title"]
            prev = out.get(d["role_id"])
            # an unfinished step beats a finished one; otherwise latest wins
            if prev is None or (prev["finished_at"] and not d["finished_at"]) or \
                    (bool(prev["finished_at"]) == bool(d["finished_at"])):
                out[d["role_id"]] = d
        return out

    # ── events ────────────────────────────────────────────────────────────
    def event(self, name: str, *, mission_id: str = "", step_id: str = "",
              role_id: str = "", detail: dict | None = None) -> dict:
        ev = {"id": _id("oe"), "mission_id": mission_id, "step_id": step_id,
              "role_id": role_id, "name": name, "detail": detail or {},
              "created_at": _now()}
        with self._conn() as c:
            c.execute("INSERT INTO org_event VALUES(?,?,?,?,?,?,?)",
                      (ev["id"], mission_id, step_id, role_id, name,
                       json.dumps(ev["detail"], default=str), ev["created_at"]))
        return ev

    def events(self, *, mission_id: str | None = None, limit: int = 50) -> list[dict]:
        q, args = "SELECT * FROM org_event", []
        if mission_id:
            q += " WHERE mission_id=?"
            args.append(mission_id)
        q += " ORDER BY created_at DESC LIMIT ?"
        args.append(limit)
        with self._conn() as c:
            rows = c.execute(q, args).fetchall()
        return [{**dict(r), "detail": json.loads(r["detail"] or "{}")} for r in rows]


def _mission(row) -> dict:
    d = dict(row)
    d["report"] = json.loads(d.get("report") or "{}")
    return d


def _step(row) -> dict:
    d = {k: row[k] for k in row.keys()}
    d["output"] = json.loads(d.get("output") or "{}")
    d["evidence"] = json.loads(d.get("evidence") or "[]")
    return d


_default: OrgStore | None = None


def default_store() -> OrgStore:
    global _default
    path = default_db_path()
    if _default is None or _default.db_path != path:
        _default = OrgStore(path)
    return _default
