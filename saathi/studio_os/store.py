"""M13 Studio store — durable projects, versioned artifacts, stages, costs,
publish receipts. data/studio_os.db. Media binaries live on disk (referenced
by storage_uri), never in SQLite.
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Optional

from saathi.studio_os.models import ProjectState, validate_transition, ArtifactStatus

ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH = ROOT / "data" / "studio_os.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS project(
  id TEXT PRIMARY KEY, owner TEXT NOT NULL, title TEXT DEFAULT '',
  objective TEXT DEFAULT '', spec TEXT DEFAULT '{}', state TEXT NOT NULL,
  workflow TEXT DEFAULT '', active_run_id TEXT DEFAULT '',
  conversation_id TEXT DEFAULT '', mission_id TEXT DEFAULT '',
  memory_namespace TEXT DEFAULT '', budget_usd REAL DEFAULT 5.0,
  cost_usd REAL DEFAULT 0, created_at REAL, updated_at REAL);
CREATE TABLE IF NOT EXISTS artifact(
  id TEXT PRIMARY KEY, project_id TEXT, run_id TEXT DEFAULT '', stage TEXT DEFAULT '',
  artifact_type TEXT, version INTEGER DEFAULT 1, status TEXT DEFAULT 'pending',
  provider TEXT DEFAULT '', source_artifacts TEXT DEFAULT '[]',
  checksum TEXT DEFAULT '', storage_uri TEXT DEFAULT '', mime_type TEXT DEFAULT '',
  duration_sec REAL DEFAULT 0, width INTEGER DEFAULT 0, height INTEGER DEFAULT 0,
  file_size INTEGER DEFAULT 0, cost_usd REAL DEFAULT 0, params TEXT DEFAULT '{}',
  content TEXT DEFAULT '', evidence TEXT DEFAULT '{}', approval_status TEXT DEFAULT 'none',
  superseded_by TEXT DEFAULT '', created_at REAL, updated_at REAL);
CREATE TABLE IF NOT EXISTS stage(
  id TEXT PRIMARY KEY, project_id TEXT, run_id TEXT, name TEXT, agent TEXT DEFAULT '',
  status TEXT DEFAULT 'pending', detail TEXT DEFAULT '', created_at REAL, finished_at REAL DEFAULT 0);
CREATE TABLE IF NOT EXISTS cost_entry(
  id TEXT PRIMARY KEY, project_id TEXT, stage TEXT DEFAULT '', kind TEXT,
  units REAL DEFAULT 0, cost_usd REAL DEFAULT 0, provider TEXT DEFAULT '', created_at REAL);
CREATE TABLE IF NOT EXISTS publish_receipt(
  id TEXT PRIMARY KEY, project_id TEXT, platform TEXT, status TEXT,
  url TEXT DEFAULT '', platform_content_id TEXT DEFAULT '', idempotency_key TEXT DEFAULT '',
  detail TEXT DEFAULT '', created_at REAL);
CREATE TABLE IF NOT EXISTS analytics_snapshot(
  id TEXT PRIMARY KEY, project_id TEXT, platform TEXT, metrics TEXT DEFAULT '{}',
  source TEXT DEFAULT '', created_at REAL);
CREATE INDEX IF NOT EXISTS idx_art_proj ON artifact(project_id, artifact_type);
CREATE INDEX IF NOT EXISTS idx_proj_owner ON project(owner);
CREATE INDEX IF NOT EXISTS idx_stage_proj ON stage(project_id, run_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_pub_idem ON publish_receipt(idempotency_key);
"""


def _now() -> float:
    return time.time()


def _id() -> str:
    return "p_" + uuid.uuid4().hex[:14]


class StudioStore:
    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path) if db_path else DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(_SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(str(self.db_path))
        c.row_factory = sqlite3.Row
        return c

    # ── projects ──────────────────────────────────────────────────────────
    def create_project(self, *, owner: str, spec: dict,
                       conversation_id: str = "", mission_id: str = "") -> str:
        pid = _id()
        now = _now()
        with self._conn() as c:
            c.execute("INSERT INTO project(id,owner,title,objective,spec,state,workflow,"
                      "conversation_id,mission_id,memory_namespace,budget_usd,created_at,"
                      "updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      (pid, owner, spec.get("title", ""), spec.get("objective", ""),
                       json.dumps(spec), ProjectState.DRAFT.value,
                       spec.get("workflow", ""), conversation_id, mission_id,
                       f"project:studio:{pid}", spec.get("budget_usd", 5.0), now, now))
        self.event(pid, "studio.project.created", {"owner": owner})
        return pid

    def get_project(self, pid: str) -> Optional[dict]:
        with self._conn() as c:
            row = c.execute("SELECT * FROM project WHERE id=?", (pid,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["spec"] = json.loads(d.get("spec") or "{}")
        return d

    def owns(self, pid: str, owner: str) -> bool:
        p = self.get_project(pid)
        return bool(p and p["owner"] == owner)

    def transition(self, pid: str, dst: ProjectState, *, actor: str = "system") -> None:
        p = self.get_project(pid)
        if not p:
            raise KeyError(pid)
        src = ProjectState(p["state"])
        validate_transition(src, dst)
        with self._conn() as c:
            c.execute("UPDATE project SET state=?, updated_at=? WHERE id=?",
                      (dst.value, _now(), pid))
        self.event(pid, "studio.project.state", {"from": src.value, "to": dst.value})

    def set_project(self, pid: str, **fields) -> None:
        cols = {"title", "objective", "workflow", "active_run_id", "budget_usd"}
        sets, args = ["updated_at=?"], [_now()]
        for k, v in fields.items():
            if k == "spec":
                sets.append("spec=?"); args.append(json.dumps(v))
            elif k in cols:
                sets.append(f"{k}=?"); args.append(v)
        args.append(pid)
        with self._conn() as c:
            c.execute(f"UPDATE project SET {','.join(sets)} WHERE id=?", args)

    def list_projects(self, *, owner: str | None = None, limit: int = 50) -> list[dict]:
        where, args = "", []
        if owner:
            where = " WHERE owner=?"; args.append(owner)
        args.append(limit)
        with self._conn() as c:
            rows = c.execute(f"SELECT id,owner,title,state,workflow,budget_usd,cost_usd,"
                             f"created_at FROM project{where} ORDER BY created_at DESC "
                             f"LIMIT ?", args).fetchall()
        return [dict(r) for r in rows]

    # ── artifacts (versioned) ─────────────────────────────────────────────
    def add_artifact(self, pid: str, *, artifact_type: str, stage: str = "",
                    run_id: str = "", provider: str = "", status: str = "ready",
                    storage_uri: str = "", checksum: str = "", mime_type: str = "",
                    duration_sec: float = 0.0, width: int = 0, height: int = 0,
                    file_size: int = 0, cost_usd: float = 0.0, content: str = "",
                    source_artifacts: list | None = None, params: dict | None = None,
                    evidence: dict | None = None) -> str:
        # versioning: new artifact of the same type in the same project gets the
        # next version and supersedes the prior latest of that type+stage
        with self._conn() as c:
            prev = c.execute("SELECT id, version FROM artifact WHERE project_id=? AND "
                             "artifact_type=? AND stage=? AND superseded_by='' "
                             "ORDER BY version DESC LIMIT 1",
                             (pid, artifact_type, stage)).fetchone()
            version = (prev["version"] + 1) if prev else 1
            aid = "a_" + uuid.uuid4().hex[:14]
            now = _now()
            c.execute("INSERT INTO artifact(id,project_id,run_id,stage,artifact_type,"
                      "version,status,provider,source_artifacts,checksum,storage_uri,"
                      "mime_type,duration_sec,width,height,file_size,cost_usd,params,"
                      "content,evidence,created_at,updated_at) VALUES"
                      "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      (aid, pid, run_id, stage, artifact_type, version, status, provider,
                       json.dumps(source_artifacts or []), checksum, storage_uri,
                       mime_type, duration_sec, width, height, file_size, cost_usd,
                       json.dumps(params or {}), content, json.dumps(evidence or {}),
                       now, now))
            if prev:
                c.execute("UPDATE artifact SET superseded_by=?, status='superseded' "
                          "WHERE id=?", (aid, prev["id"]))
        self.event(pid, "studio.artifact.created",
                   {"type": artifact_type, "version": version, "provider": provider})
        return aid

    def get_artifact(self, aid: str) -> Optional[dict]:
        with self._conn() as c:
            row = c.execute("SELECT * FROM artifact WHERE id=?", (aid,)).fetchone()
        if not row:
            return None
        d = dict(row)
        for k in ("source_artifacts", "params", "evidence"):
            d[k] = json.loads(d.get(k) or ("[]" if k == "source_artifacts" else "{}"))
        return d

    def artifact_versions(self, pid: str, artifact_type: str, stage: str = "") -> list[dict]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM artifact WHERE project_id=? AND artifact_type=? "
                             "AND stage=? ORDER BY version", (pid, artifact_type, stage)).fetchall()
        return [dict(r) for r in rows]

    def list_artifacts(self, pid: str, *, latest_only: bool = True) -> list[dict]:
        q = "SELECT * FROM artifact WHERE project_id=?"
        if latest_only:
            q += " AND superseded_by=''"
        q += " ORDER BY created_at"
        with self._conn() as c:
            rows = c.execute(q, (pid,)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            for k in ("source_artifacts", "params", "evidence"):
                d[k] = json.loads(d.get(k) or ("[]" if k == "source_artifacts" else "{}"))
            out.append(d)
        return out

    def set_artifact_approval(self, aid: str, status: str) -> None:
        with self._conn() as c:
            c.execute("UPDATE artifact SET approval_status=?, updated_at=? WHERE id=?",
                      (status, _now(), aid))

    # ── stages ────────────────────────────────────────────────────────────
    def add_stage(self, pid: str, run_id: str, name: str, agent: str = "") -> str:
        sid = "s_" + uuid.uuid4().hex[:12]
        with self._conn() as c:
            c.execute("INSERT INTO stage(id,project_id,run_id,name,agent,status,created_at)"
                      " VALUES(?,?,?,?,?,?,?)", (sid, pid, run_id, name, agent,
                                                 "running", _now()))
        self.event(pid, "studio.stage.started", {"stage": name, "agent": agent})
        return sid

    def finish_stage(self, sid: str, status: str, detail: str = "") -> None:
        with self._conn() as c:
            row = c.execute("SELECT project_id, name FROM stage WHERE id=?", (sid,)).fetchone()
            c.execute("UPDATE stage SET status=?, detail=?, finished_at=? WHERE id=?",
                      (status, detail, _now(), sid))
        if row:
            self.event(row["project_id"],
                       "studio.stage.completed" if status == "done" else "studio.stage.failed",
                       {"stage": row["name"]})

    def list_stages(self, pid: str) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT * FROM stage WHERE project_id=? ORDER BY created_at",
                (pid,)).fetchall()]

    # ── costs ─────────────────────────────────────────────────────────────
    def add_cost(self, pid: str, *, kind: str, units: float, cost_usd: float,
                stage: str = "", provider: str = "") -> None:
        with self._conn() as c:
            c.execute("INSERT INTO cost_entry VALUES(?,?,?,?,?,?,?,?)",
                      ("c_" + uuid.uuid4().hex[:12], pid, stage, kind, units, cost_usd,
                       provider, _now()))
            c.execute("UPDATE project SET cost_usd=cost_usd+? WHERE id=?", (cost_usd, pid))

    def cost_summary(self, pid: str) -> dict:
        with self._conn() as c:
            total = c.execute("SELECT cost_usd, budget_usd FROM project WHERE id=?",
                              (pid,)).fetchone()
            by_kind = c.execute("SELECT kind, SUM(cost_usd) s, SUM(units) u FROM cost_entry "
                                "WHERE project_id=? GROUP BY kind", (pid,)).fetchall()
        return {"total_usd": round(total["cost_usd"], 4) if total else 0,
                "budget_usd": total["budget_usd"] if total else 0,
                "by_kind": {r["kind"]: {"cost": round(r["s"], 4), "units": r["u"]}
                            for r in by_kind}}

    # ── publish receipts ──────────────────────────────────────────────────
    def add_receipt(self, pid: str, *, platform: str, status: str, url: str = "",
                   platform_content_id: str = "", idempotency_key: str = "",
                   detail: str = "") -> str:
        rid = "r_" + uuid.uuid4().hex[:12]
        with self._conn() as c:
            c.execute("INSERT INTO publish_receipt VALUES(?,?,?,?,?,?,?,?,?)",
                      (rid, pid, platform, status, url, platform_content_id,
                       idempotency_key or rid, detail, _now()))
        self.event(pid, "studio.publish.completed" if status == "published"
                   else "studio.publish.failed", {"platform": platform, "status": status})
        return rid

    def receipt_by_idempotency(self, key: str) -> Optional[dict]:
        with self._conn() as c:
            row = c.execute("SELECT * FROM publish_receipt WHERE idempotency_key=?",
                            (key,)).fetchone()
        return dict(row) if row else None

    def receipts(self, pid: str) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT * FROM publish_receipt WHERE project_id=?", (pid,)).fetchall()]

    # ── analytics ─────────────────────────────────────────────────────────
    def add_analytics(self, pid: str, platform: str, metrics: dict, source: str) -> None:
        with self._conn() as c:
            c.execute("INSERT INTO analytics_snapshot VALUES(?,?,?,?,?,?)",
                      ("an_" + uuid.uuid4().hex[:12], pid, platform, json.dumps(metrics),
                       source, _now()))

    def analytics(self, pid: str) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM analytics_snapshot WHERE project_id=? "
                             "ORDER BY created_at DESC", (pid,)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["metrics"] = json.loads(d.get("metrics") or "{}")
            out.append(d)
        return out

    # ── events ────────────────────────────────────────────────────────────
    def event(self, pid: str, name: str, payload: dict | None = None) -> None:
        try:
            from saathi.events import bus
            bus.publish_sync(name, {"project_id": pid, **(payload or {})})
        except Exception:
            pass


_default: StudioStore | None = None


def default_store() -> StudioStore:
    global _default
    if _default is None:
        _default = StudioStore()
    return _default
