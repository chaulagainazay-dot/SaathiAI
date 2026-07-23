"""M50 PlatformStore — SQLite persistence for tenancy, memberships, approvals, audit.

Separate from M49 tool idempotency DB and legacy security.db. Single-host safe.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Callable

from saathi.platform.models import (
    ApprovalRecord,
    ApprovalStatus,
    MissionLinkRecord,
    OrganizationRecord,
    PlatformRole,
    ProjectRecord,
    SessionRecord,
    UserRecord,
    WorkspaceRecord,
    new_id,
)

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_DB = ROOT / "data" / "platform" / "platform.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    email TEXT UNIQUE,
    name TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    org_id TEXT NOT NULL DEFAULT '',
    workspace_id TEXT NOT NULL DEFAULT '',
    role TEXT NOT NULL DEFAULT 'viewer',
    created_at REAL NOT NULL,
    last_seen REAL NOT NULL,
    expires_at REAL NOT NULL,
    revoked INTEGER NOT NULL DEFAULT 0,
    label TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS organizations (
    org_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    owner_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_at REAL NOT NULL,
    FOREIGN KEY (owner_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS memberships (
    org_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'viewer',
    created_at REAL NOT NULL,
    PRIMARY KEY (org_id, user_id),
    FOREIGN KEY (org_id) REFERENCES organizations(org_id),
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS workspaces (
    workspace_id TEXT PRIMARY KEY,
    org_id TEXT NOT NULL,
    name TEXT NOT NULL,
    created_by TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_at REAL NOT NULL,
    FOREIGN KEY (org_id) REFERENCES organizations(org_id)
);

CREATE TABLE IF NOT EXISTS projects (
    project_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    org_id TEXT NOT NULL,
    name TEXT NOT NULL,
    owner_id TEXT NOT NULL,
    mission_key TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    FOREIGN KEY (workspace_id) REFERENCES workspaces(workspace_id),
    FOREIGN KEY (org_id) REFERENCES organizations(org_id)
);

CREATE TABLE IF NOT EXISTS missions (
    mission_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    org_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    key TEXT NOT NULL,
    name TEXT NOT NULL,
    owner_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_at REAL NOT NULL,
    UNIQUE (org_id, key),
    FOREIGN KEY (project_id) REFERENCES projects(project_id)
);

CREATE TABLE IF NOT EXISTS approvals (
    approval_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    org_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    project_id TEXT NOT NULL DEFAULT '',
    mission_id TEXT NOT NULL DEFAULT '',
    tool_id TEXT NOT NULL,
    action TEXT NOT NULL DEFAULT '',
    target_resource TEXT NOT NULL DEFAULT '',
    authority TEXT NOT NULL DEFAULT '',
    side_effect_class TEXT NOT NULL DEFAULT '',
    capability TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    requested_by TEXT NOT NULL DEFAULT '',
    decided_by TEXT NOT NULL DEFAULT '',
    reason TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL DEFAULT 0,
    decided_at REAL NOT NULL DEFAULT 0,
    consumed_at REAL NOT NULL DEFAULT 0,
    run_id TEXT NOT NULL DEFAULT '',
    tool_version TEXT NOT NULL DEFAULT '',
    connector TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    event TEXT NOT NULL,
    user_id TEXT NOT NULL DEFAULT '',
    role TEXT NOT NULL DEFAULT '',
    org_id TEXT NOT NULL DEFAULT '',
    workspace_id TEXT NOT NULL DEFAULT '',
    project_id TEXT NOT NULL DEFAULT '',
    mission_id TEXT NOT NULL DEFAULT '',
    run_id TEXT NOT NULL DEFAULT '',
    tool_id TEXT NOT NULL DEFAULT '',
    approval_id TEXT NOT NULL DEFAULT '',
    authority TEXT NOT NULL DEFAULT '',
    outcome TEXT NOT NULL DEFAULT '',
    evidence TEXT NOT NULL DEFAULT '',
    detail TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS platform_config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at REAL NOT NULL,
    updated_by TEXT NOT NULL DEFAULT ''
);
"""

_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_plat_sess_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_plat_sess_hash ON sessions(token_hash);
CREATE INDEX IF NOT EXISTS idx_plat_mem_user ON memberships(user_id);
CREATE INDEX IF NOT EXISTS idx_plat_ws_org ON workspaces(org_id);
CREATE INDEX IF NOT EXISTS idx_plat_proj_ws ON projects(workspace_id);
CREATE INDEX IF NOT EXISTS idx_plat_proj_org ON projects(org_id);
CREATE INDEX IF NOT EXISTS idx_plat_mis_proj ON missions(project_id);
CREATE INDEX IF NOT EXISTS idx_plat_appr_status ON approvals(status, org_id);
CREATE INDEX IF NOT EXISTS idx_plat_audit_ts ON audit_events(ts DESC);
CREATE INDEX IF NOT EXISTS idx_plat_audit_user ON audit_events(user_id, ts DESC);
"""


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class PlatformStore:
    def __init__(self, db_path: Path | str | None = None, *, now: Callable[[], float] = time.time):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._now = now
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.executescript(_SCHEMA)
        self._conn.executescript(_INDEXES)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # ── users ─────────────────────────────────────────────────────────────
    def create_user(self, *, email: str = "", name: str = "", user_id: str = "") -> UserRecord:
        uid = user_id or new_id("usr_")
        now = self._now()
        self._conn.execute(
            "INSERT INTO users (user_id, email, name, status, created_at, updated_at) VALUES (?,?,?,?,?,?)",
            (uid, email or None, name or "", "active", now, now),
        )
        self._conn.commit()
        return UserRecord(user_id=uid, email=email, name=name, created_at=now, updated_at=now)

    def get_user(self, user_id: str) -> UserRecord | None:
        row = self._conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        return self._user_row(row) if row else None

    def get_user_by_email(self, email: str) -> UserRecord | None:
        row = self._conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        return self._user_row(row) if row else None

    def list_users(self) -> list[UserRecord]:
        rows = self._conn.execute("SELECT * FROM users ORDER BY created_at").fetchall()
        return [self._user_row(r) for r in rows]

    def _user_row(self, row: sqlite3.Row) -> UserRecord:
        return UserRecord(
            user_id=row["user_id"],
            email=row["email"] or "",
            name=row["name"] or "",
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    # ── sessions ──────────────────────────────────────────────────────────
    def create_session(
        self,
        user_id: str,
        token: str,
        *,
        org_id: str = "",
        workspace_id: str = "",
        role: str = PlatformRole.VIEWER.value,
        ttl_sec: float = 86400.0,
        label: str = "",
    ) -> tuple[SessionRecord, str]:
        """Returns (session, raw_token). Raw token shown once."""
        now = self._now()
        th = hash_token(token)
        sid = new_id("ses_")
        exp = now + float(ttl_sec)
        self._conn.execute(
            "INSERT INTO sessions (session_id, user_id, token_hash, org_id, workspace_id, role,"
            " created_at, last_seen, expires_at, revoked, label) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (sid, user_id, th, org_id, workspace_id, role, now, now, exp, 0, label),
        )
        self._conn.commit()
        rec = SessionRecord(
            session_id=sid,
            user_id=user_id,
            token_hash=th,
            org_id=org_id,
            workspace_id=workspace_id,
            role=role,
            created_at=now,
            last_seen=now,
            expires_at=exp,
            revoked=False,
            label=label,
        )
        return rec, token

    def session_by_token(self, token: str) -> SessionRecord | None:
        th = hash_token(token)
        row = self._conn.execute(
            "SELECT * FROM sessions WHERE token_hash=? AND revoked=0", (th,)
        ).fetchone()
        if not row:
            return None
        rec = self._session_row(row)
        if not rec.is_active(self._now()):
            return None
        return rec

    def touch_session(self, session_id: str) -> None:
        self._conn.execute(
            "UPDATE sessions SET last_seen=? WHERE session_id=?",
            (self._now(), session_id),
        )
        self._conn.commit()

    def revoke_session(self, session_id: str) -> bool:
        cur = self._conn.execute(
            "UPDATE sessions SET revoked=1 WHERE session_id=?", (session_id,)
        )
        self._conn.commit()
        return cur.rowcount > 0

    def revoke_user_sessions(self, user_id: str, *, except_session: str = "") -> int:
        if except_session:
            cur = self._conn.execute(
                "UPDATE sessions SET revoked=1 WHERE user_id=? AND session_id!=? AND revoked=0",
                (user_id, except_session),
            )
        else:
            cur = self._conn.execute(
                "UPDATE sessions SET revoked=1 WHERE user_id=? AND revoked=0",
                (user_id,),
            )
        self._conn.commit()
        return cur.rowcount

    def list_sessions(self, user_id: str) -> list[SessionRecord]:
        now = self._now()
        rows = self._conn.execute(
            "SELECT * FROM sessions WHERE user_id=? AND revoked=0 AND expires_at > ? ORDER BY last_seen DESC",
            (user_id, now),
        ).fetchall()
        return [self._session_row(r) for r in rows]

    def _session_row(self, row: sqlite3.Row) -> SessionRecord:
        return SessionRecord(
            session_id=row["session_id"],
            user_id=row["user_id"],
            token_hash=row["token_hash"],
            org_id=row["org_id"] or "",
            workspace_id=row["workspace_id"] or "",
            role=row["role"] or PlatformRole.VIEWER.value,
            created_at=row["created_at"],
            last_seen=row["last_seen"],
            expires_at=row["expires_at"],
            revoked=bool(row["revoked"]),
            label=row["label"] or "",
        )

    # ── orgs / membership ─────────────────────────────────────────────────
    def create_org(self, name: str, owner_id: str, *, org_id: str = "") -> OrganizationRecord:
        oid = org_id or new_id("org_")
        now = self._now()
        self._conn.execute(
            "INSERT INTO organizations (org_id, name, owner_id, status, created_at) VALUES (?,?,?,?,?)",
            (oid, name, owner_id, "active", now),
        )
        self._conn.execute(
            "INSERT INTO memberships (org_id, user_id, role, created_at) VALUES (?,?,?,?)",
            (oid, owner_id, PlatformRole.OWNER.value, now),
        )
        self._conn.commit()
        return OrganizationRecord(org_id=oid, name=name, owner_id=owner_id, created_at=now)

    def get_org(self, org_id: str) -> OrganizationRecord | None:
        row = self._conn.execute("SELECT * FROM organizations WHERE org_id=?", (org_id,)).fetchone()
        if not row:
            return None
        return OrganizationRecord(
            org_id=row["org_id"],
            name=row["name"],
            owner_id=row["owner_id"],
            status=row["status"],
            created_at=row["created_at"],
        )

    def add_member(self, org_id: str, user_id: str, role: str) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO memberships (org_id, user_id, role, created_at) VALUES (?,?,?,?)",
            (org_id, user_id, role, self._now()),
        )
        self._conn.commit()

    def membership_role(self, org_id: str, user_id: str) -> str | None:
        row = self._conn.execute(
            "SELECT role FROM memberships WHERE org_id=? AND user_id=?",
            (org_id, user_id),
        ).fetchone()
        return row["role"] if row else None

    def list_orgs_for_user(self, user_id: str) -> list[OrganizationRecord]:
        rows = self._conn.execute(
            "SELECT o.* FROM organizations o JOIN memberships m ON o.org_id=m.org_id "
            "WHERE m.user_id=? ORDER BY o.created_at",
            (user_id,),
        ).fetchall()
        return [
            OrganizationRecord(
                org_id=r["org_id"],
                name=r["name"],
                owner_id=r["owner_id"],
                status=r["status"],
                created_at=r["created_at"],
            )
            for r in rows
        ]

    # ── workspaces ────────────────────────────────────────────────────────
    def create_workspace(
        self, org_id: str, name: str, created_by: str, *, workspace_id: str = ""
    ) -> WorkspaceRecord:
        wid = workspace_id or new_id("ws_")
        now = self._now()
        self._conn.execute(
            "INSERT INTO workspaces (workspace_id, org_id, name, created_by, status, created_at)"
            " VALUES (?,?,?,?,?,?)",
            (wid, org_id, name, created_by, "active", now),
        )
        self._conn.commit()
        return WorkspaceRecord(
            workspace_id=wid, org_id=org_id, name=name, created_by=created_by, created_at=now
        )

    def get_workspace(self, workspace_id: str) -> WorkspaceRecord | None:
        row = self._conn.execute(
            "SELECT * FROM workspaces WHERE workspace_id=?", (workspace_id,)
        ).fetchone()
        if not row:
            return None
        return WorkspaceRecord(
            workspace_id=row["workspace_id"],
            org_id=row["org_id"],
            name=row["name"],
            created_by=row["created_by"],
            status=row["status"],
            created_at=row["created_at"],
        )

    def list_workspaces(self, org_id: str) -> list[WorkspaceRecord]:
        rows = self._conn.execute(
            "SELECT * FROM workspaces WHERE org_id=? ORDER BY created_at", (org_id,)
        ).fetchall()
        return [
            WorkspaceRecord(
                workspace_id=r["workspace_id"],
                org_id=r["org_id"],
                name=r["name"],
                created_by=r["created_by"],
                status=r["status"],
                created_at=r["created_at"],
            )
            for r in rows
        ]

    # ── projects ──────────────────────────────────────────────────────────
    def create_project(
        self,
        *,
        workspace_id: str,
        org_id: str,
        name: str,
        owner_id: str,
        mission_key: str = "",
        project_id: str = "",
    ) -> ProjectRecord:
        pid = project_id or new_id("prj_")
        now = self._now()
        self._conn.execute(
            "INSERT INTO projects (project_id, workspace_id, org_id, name, owner_id, mission_key,"
            " status, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (pid, workspace_id, org_id, name, owner_id, mission_key, "active", now, now),
        )
        self._conn.commit()
        return ProjectRecord(
            project_id=pid,
            workspace_id=workspace_id,
            org_id=org_id,
            name=name,
            owner_id=owner_id,
            mission_key=mission_key,
            created_at=now,
            updated_at=now,
        )

    def get_project(self, project_id: str) -> ProjectRecord | None:
        row = self._conn.execute(
            "SELECT * FROM projects WHERE project_id=?", (project_id,)
        ).fetchone()
        if not row:
            return None
        return ProjectRecord(
            project_id=row["project_id"],
            workspace_id=row["workspace_id"],
            org_id=row["org_id"],
            name=row["name"],
            owner_id=row["owner_id"],
            mission_key=row["mission_key"] or "",
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def list_projects(self, *, org_id: str = "", workspace_id: str = "") -> list[ProjectRecord]:
        if workspace_id:
            rows = self._conn.execute(
                "SELECT * FROM projects WHERE workspace_id=? ORDER BY created_at",
                (workspace_id,),
            ).fetchall()
        elif org_id:
            rows = self._conn.execute(
                "SELECT * FROM projects WHERE org_id=? ORDER BY created_at", (org_id,)
            ).fetchall()
        else:
            rows = self._conn.execute("SELECT * FROM projects ORDER BY created_at").fetchall()
        out = []
        for row in rows:
            out.append(
                ProjectRecord(
                    project_id=row["project_id"],
                    workspace_id=row["workspace_id"],
                    org_id=row["org_id"],
                    name=row["name"],
                    owner_id=row["owner_id"],
                    mission_key=row["mission_key"] or "",
                    status=row["status"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                )
            )
        return out

    # ── missions ──────────────────────────────────────────────────────────
    def create_mission(
        self,
        *,
        project_id: str,
        org_id: str,
        workspace_id: str,
        key: str,
        name: str,
        owner_id: str,
        mission_id: str = "",
    ) -> MissionLinkRecord:
        mid = mission_id or new_id("mis_")
        now = self._now()
        self._conn.execute(
            "INSERT INTO missions (mission_id, project_id, org_id, workspace_id, key, name,"
            " owner_id, status, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (mid, project_id, org_id, workspace_id, key, name, owner_id, "active", now),
        )
        self._conn.commit()
        return MissionLinkRecord(
            mission_id=mid,
            project_id=project_id,
            org_id=org_id,
            workspace_id=workspace_id,
            key=key,
            name=name,
            owner_id=owner_id,
            created_at=now,
        )

    def get_mission(self, mission_id: str) -> MissionLinkRecord | None:
        row = self._conn.execute(
            "SELECT * FROM missions WHERE mission_id=?", (mission_id,)
        ).fetchone()
        if not row:
            return None
        return MissionLinkRecord(
            mission_id=row["mission_id"],
            project_id=row["project_id"],
            org_id=row["org_id"],
            workspace_id=row["workspace_id"],
            key=row["key"],
            name=row["name"],
            owner_id=row["owner_id"],
            status=row["status"],
            created_at=row["created_at"],
        )

    def list_missions(self, *, project_id: str = "", org_id: str = "") -> list[MissionLinkRecord]:
        if project_id:
            rows = self._conn.execute(
                "SELECT * FROM missions WHERE project_id=? ORDER BY created_at", (project_id,)
            ).fetchall()
        elif org_id:
            rows = self._conn.execute(
                "SELECT * FROM missions WHERE org_id=? ORDER BY created_at", (org_id,)
            ).fetchall()
        else:
            rows = self._conn.execute("SELECT * FROM missions ORDER BY created_at").fetchall()
        return [
            MissionLinkRecord(
                mission_id=r["mission_id"],
                project_id=r["project_id"],
                org_id=r["org_id"],
                workspace_id=r["workspace_id"],
                key=r["key"],
                name=r["name"],
                owner_id=r["owner_id"],
                status=r["status"],
                created_at=r["created_at"],
            )
            for r in rows
        ]

    # ── approvals ─────────────────────────────────────────────────────────
    def save_approval(self, a: ApprovalRecord) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO approvals ("
            "approval_id,user_id,org_id,workspace_id,project_id,mission_id,tool_id,action,"
            "target_resource,authority,side_effect_class,capability,status,requested_by,"
            "decided_by,reason,created_at,expires_at,decided_at,consumed_at,run_id,"
            "tool_version,connector) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                a.approval_id,
                a.user_id,
                a.org_id,
                a.workspace_id,
                a.project_id,
                a.mission_id,
                a.tool_id,
                a.action,
                a.target_resource,
                a.authority,
                a.side_effect_class,
                a.capability,
                a.status,
                a.requested_by,
                a.decided_by,
                a.reason,
                a.created_at,
                a.expires_at,
                a.decided_at,
                a.consumed_at,
                a.run_id,
                a.tool_version,
                a.connector,
            ),
        )
        self._conn.commit()

    def get_approval(self, approval_id: str) -> ApprovalRecord | None:
        row = self._conn.execute(
            "SELECT * FROM approvals WHERE approval_id=?", (approval_id,)
        ).fetchone()
        return self._approval_row(row) if row else None

    def list_approvals(
        self,
        *,
        org_id: str = "",
        status: str = "",
        user_id: str = "",
        limit: int = 100,
    ) -> list[ApprovalRecord]:
        sql = "SELECT * FROM approvals WHERE 1=1"
        args: list[Any] = []
        if org_id:
            sql += " AND org_id=?"; args.append(org_id)
        if status:
            sql += " AND status=?"; args.append(status)
        if user_id:
            sql += " AND user_id=?"; args.append(user_id)
        sql += " ORDER BY created_at DESC LIMIT ?"
        args.append(int(limit))
        rows = self._conn.execute(sql, args).fetchall()
        return [self._approval_row(r) for r in rows]

    def expire_stale_approvals(self) -> int:
        now = self._now()
        cur = self._conn.execute(
            "UPDATE approvals SET status=? WHERE status=? AND expires_at > 0 AND expires_at < ?",
            (ApprovalStatus.EXPIRED.value, ApprovalStatus.PENDING.value, now),
        )
        # also expire approved-but-unused past expiry
        cur2 = self._conn.execute(
            "UPDATE approvals SET status=? WHERE status=? AND expires_at > 0 AND expires_at < ?",
            (ApprovalStatus.EXPIRED.value, ApprovalStatus.APPROVED.value, now),
        )
        self._conn.commit()
        return (cur.rowcount or 0) + (cur2.rowcount or 0)

    def _approval_row(self, row: sqlite3.Row) -> ApprovalRecord:
        return ApprovalRecord(
            approval_id=row["approval_id"],
            user_id=row["user_id"],
            org_id=row["org_id"],
            workspace_id=row["workspace_id"],
            project_id=row["project_id"] or "",
            mission_id=row["mission_id"] or "",
            tool_id=row["tool_id"],
            action=row["action"] or "",
            target_resource=row["target_resource"] or "",
            authority=row["authority"] or "",
            side_effect_class=row["side_effect_class"] or "",
            capability=row["capability"] or "",
            status=row["status"],
            requested_by=row["requested_by"] or "",
            decided_by=row["decided_by"] or "",
            reason=row["reason"] or "",
            created_at=row["created_at"],
            expires_at=row["expires_at"] or 0,
            decided_at=row["decided_at"] or 0,
            consumed_at=row["consumed_at"] or 0,
            run_id=row["run_id"] or "",
            tool_version=row["tool_version"] or "",
            connector=row["connector"] or "",
        )

    # ── audit ─────────────────────────────────────────────────────────────
    def append_audit(
        self,
        event: str,
        *,
        user_id: str = "",
        role: str = "",
        org_id: str = "",
        workspace_id: str = "",
        project_id: str = "",
        mission_id: str = "",
        run_id: str = "",
        tool_id: str = "",
        approval_id: str = "",
        authority: str = "",
        outcome: str = "",
        evidence: str = "",
        detail: dict | None = None,
    ) -> None:
        self._conn.execute(
            "INSERT INTO audit_events (ts, event, user_id, role, org_id, workspace_id, project_id,"
            " mission_id, run_id, tool_id, approval_id, authority, outcome, evidence, detail)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                self._now(),
                event,
                user_id,
                role,
                org_id,
                workspace_id,
                project_id,
                mission_id,
                run_id,
                tool_id,
                approval_id,
                authority,
                outcome,
                evidence,
                json.dumps(detail or {}, default=str)[:4000],
            ),
        )
        self._conn.commit()

    def list_audit(
        self, *, user_id: str = "", org_id: str = "", limit: int = 100
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM audit_events WHERE 1=1"
        args: list[Any] = []
        if user_id:
            sql += " AND user_id=?"; args.append(user_id)
        if org_id:
            sql += " AND org_id=?"; args.append(org_id)
        sql += " ORDER BY ts DESC LIMIT ?"
        args.append(int(limit))
        rows = self._conn.execute(sql, args).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            try:
                d["detail"] = json.loads(d.get("detail") or "{}")
            except Exception:
                pass
            out.append(d)
        return out

    # ── config ────────────────────────────────────────────────────────────
    def set_config(self, key: str, value: Any, *, updated_by: str = "") -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO platform_config (key, value, updated_at, updated_by) VALUES (?,?,?,?)",
            (key, json.dumps(value), self._now(), updated_by),
        )
        self._conn.commit()

    def get_config(self, key: str, default: Any = None) -> Any:
        row = self._conn.execute(
            "SELECT value FROM platform_config WHERE key=?", (key,)
        ).fetchone()
        if not row:
            return default
        try:
            return json.loads(row["value"])
        except Exception:
            return row["value"]

    def all_config(self) -> dict[str, Any]:
        rows = self._conn.execute("SELECT key, value FROM platform_config").fetchall()
        out: dict[str, Any] = {}
        for r in rows:
            try:
                out[r["key"]] = json.loads(r["value"])
            except Exception:
                out[r["key"]] = r["value"]
        return out
