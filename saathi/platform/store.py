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
        self._migrate_m51()
        self._conn.commit()

    def _migrate_m51(self) -> None:
        """Idempotent M51 schema extensions (single-host SQLite)."""
        # sessions hardening columns
        sess_cols = {
            r[1] for r in self._conn.execute("PRAGMA table_info(sessions)").fetchall()
        }
        for col, decl in (
            ("auth_method", "TEXT NOT NULL DEFAULT ''"),
            ("idle_expires_at", "REAL NOT NULL DEFAULT 0"),
            ("revoked_at", "REAL NOT NULL DEFAULT 0"),
            ("revocation_reason", "TEXT NOT NULL DEFAULT ''"),
            ("session_version", "INTEGER NOT NULL DEFAULT 1"),
            ("ua_hash", "TEXT NOT NULL DEFAULT ''"),
            ("absolute_expires_at", "REAL NOT NULL DEFAULT 0"),
        ):
            if col not in sess_cols:
                self._conn.execute(f"ALTER TABLE sessions ADD COLUMN {col} {decl}")

        mem_cols = {
            r[1] for r in self._conn.execute("PRAGMA table_info(memberships)").fetchall()
        }
        if "status" not in mem_cols:
            self._conn.execute(
                "ALTER TABLE memberships ADD COLUMN status TEXT NOT NULL DEFAULT 'active'"
            )

        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS credentials (
                user_id TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL DEFAULT '',
                force_reset INTEGER NOT NULL DEFAULT 0,
                failed_logins INTEGER NOT NULL DEFAULT 0,
                locked_until REAL NOT NULL DEFAULT 0,
                last_verified_at REAL NOT NULL DEFAULT 0,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );
            CREATE TABLE IF NOT EXISTS recovery_codes (
                code_hash TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                label TEXT NOT NULL DEFAULT 'PRIVATE_ALPHA_ONLY',
                created_at REAL NOT NULL,
                expires_at REAL NOT NULL,
                used INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );
            CREATE TABLE IF NOT EXISTS invitations (
                invite_id TEXT PRIMARY KEY,
                org_id TEXT NOT NULL,
                workspace_id TEXT NOT NULL DEFAULT '',
                email TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'viewer',
                inviter_id TEXT NOT NULL,
                token_hash TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at REAL NOT NULL,
                expires_at REAL NOT NULL,
                accepted_at REAL NOT NULL DEFAULT 0,
                accepted_user_id TEXT NOT NULL DEFAULT '',
                FOREIGN KEY (org_id) REFERENCES organizations(org_id)
            );
            CREATE TABLE IF NOT EXISTS rate_limits (
                surface TEXT NOT NULL,
                key TEXT NOT NULL,
                failures INTEGER NOT NULL DEFAULT 0,
                window_start REAL NOT NULL DEFAULT 0,
                locked_until REAL NOT NULL DEFAULT 0,
                PRIMARY KEY (surface, key)
            );
            CREATE TABLE IF NOT EXISTS external_identity_links (
                link_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                provider TEXT NOT NULL,
                external_subject TEXT NOT NULL,
                created_at REAL NOT NULL,
                last_verified_at REAL NOT NULL DEFAULT 0,
                revoked INTEGER NOT NULL DEFAULT 0,
                UNIQUE (provider, external_subject),
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );
            CREATE TABLE IF NOT EXISTS mission_legacy_links (
                mission_id TEXT NOT NULL,
                legacy_mission_key TEXT NOT NULL,
                org_id TEXT NOT NULL,
                workspace_id TEXT NOT NULL,
                created_at REAL NOT NULL,
                PRIMARY KEY (mission_id, legacy_mission_key)
            );
            CREATE INDEX IF NOT EXISTS idx_plat_invite_org ON invitations(org_id, status);
            CREATE INDEX IF NOT EXISTS idx_plat_invite_hash ON invitations(token_hash);
            """
        )

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
        idle_sec: float = 3600.0,
        label: str = "",
        auth_method: str = "",
        ua_hash: str = "",
        session_version: int = 1,
    ) -> tuple[SessionRecord, str]:
        """Returns (session, raw_token). Raw token shown once — never log it."""
        now = self._now()
        th = hash_token(token)
        sid = new_id("ses_")
        abs_exp = now + float(ttl_sec)
        idle_exp = now + float(idle_sec)
        self._conn.execute(
            "INSERT INTO sessions (session_id, user_id, token_hash, org_id, workspace_id, role,"
            " created_at, last_seen, expires_at, revoked, label, auth_method, idle_expires_at,"
            " revoked_at, revocation_reason, session_version, ua_hash, absolute_expires_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                sid,
                user_id,
                th,
                org_id,
                workspace_id,
                role,
                now,
                now,
                abs_exp,
                0,
                label,
                auth_method,
                idle_exp,
                0,
                "",
                int(session_version),
                ua_hash,
                abs_exp,
            ),
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
            expires_at=abs_exp,
            revoked=False,
            label=label,
            auth_method=auth_method,
            idle_expires_at=idle_exp,
            session_version=int(session_version),
            ua_hash=ua_hash,
            absolute_expires_at=abs_exp,
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

    def touch_session(self, session_id: str, *, idle_sec: float = 3600.0) -> None:
        now = self._now()
        self._conn.execute(
            "UPDATE sessions SET last_seen=?, idle_expires_at=? WHERE session_id=?",
            (now, now + float(idle_sec), session_id),
        )
        self._conn.commit()

    def rotate_session_token(
        self, session_id: str, new_token: str, *, idle_sec: float = 3600.0
    ) -> bool:
        """Replace token hash and bump version; old token becomes unusable."""
        now = self._now()
        th = hash_token(new_token)
        cur = self._conn.execute(
            "UPDATE sessions SET token_hash=?, session_version=session_version+1,"
            " last_seen=?, idle_expires_at=? WHERE session_id=? AND revoked=0",
            (th, now, now + float(idle_sec), session_id),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def update_session_context(
        self, session_id: str, *, org_id: str, workspace_id: str, role: str
    ) -> bool:
        cur = self._conn.execute(
            "UPDATE sessions SET org_id=?, workspace_id=?, role=? WHERE session_id=? AND revoked=0",
            (org_id, workspace_id, role, session_id),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def revoke_session(self, session_id: str, *, reason: str = "logout") -> bool:
        now = self._now()
        cur = self._conn.execute(
            "UPDATE sessions SET revoked=1, revoked_at=?, revocation_reason=? WHERE session_id=?",
            (now, reason[:200], session_id),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def revoke_user_sessions(
        self, user_id: str, *, except_session: str = "", reason: str = "bulk_revoke"
    ) -> int:
        now = self._now()
        if except_session:
            cur = self._conn.execute(
                "UPDATE sessions SET revoked=1, revoked_at=?, revocation_reason=?"
                " WHERE user_id=? AND session_id!=? AND revoked=0",
                (now, reason[:200], user_id, except_session),
            )
        else:
            cur = self._conn.execute(
                "UPDATE sessions SET revoked=1, revoked_at=?, revocation_reason=?"
                " WHERE user_id=? AND revoked=0",
                (now, reason[:200], user_id),
            )
        self._conn.commit()
        return cur.rowcount

    def list_sessions(self, user_id: str) -> list[SessionRecord]:
        now = self._now()
        rows = self._conn.execute(
            "SELECT * FROM sessions WHERE user_id=? AND revoked=0 AND expires_at > ?"
            " ORDER BY last_seen DESC",
            (user_id, now),
        ).fetchall()
        return [self._session_row(r) for r in rows]

    def get_session(self, session_id: str) -> SessionRecord | None:
        row = self._conn.execute(
            "SELECT * FROM sessions WHERE session_id=?", (session_id,)
        ).fetchone()
        return self._session_row(row) if row else None

    def _session_row(self, row: sqlite3.Row) -> SessionRecord:
        keys = row.keys()
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
            auth_method=(row["auth_method"] if "auth_method" in keys else "") or "",
            idle_expires_at=float(row["idle_expires_at"] if "idle_expires_at" in keys else 0) or 0.0,
            revoked_at=float(row["revoked_at"] if "revoked_at" in keys else 0) or 0.0,
            revocation_reason=(row["revocation_reason"] if "revocation_reason" in keys else "") or "",
            session_version=int(row["session_version"] if "session_version" in keys else 1) or 1,
            ua_hash=(row["ua_hash"] if "ua_hash" in keys else "") or "",
            absolute_expires_at=float(
                row["absolute_expires_at"] if "absolute_expires_at" in keys else 0
            )
            or 0.0,
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


    # ── M51 credentials ───────────────────────────────────────────────────
    def set_password_hash(self, user_id: str, password_hash: str, *, force_reset: bool = False) -> None:
        now = self._now()
        self._conn.execute(
            "INSERT INTO credentials (user_id, password_hash, force_reset, failed_logins,"
            " locked_until, last_verified_at, created_at, updated_at)"
            " VALUES (?,?,?,0,0,0,?,?)"
            " ON CONFLICT(user_id) DO UPDATE SET password_hash=excluded.password_hash,"
            " force_reset=excluded.force_reset, updated_at=excluded.updated_at,"
            " failed_logins=0, locked_until=0",
            (user_id, password_hash, 1 if force_reset else 0, now, now),
        )
        self._conn.commit()

    def get_credential(self, user_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM credentials WHERE user_id=?", (user_id,)
        ).fetchone()
        return dict(row) if row else None

    def mark_credential_verified(self, user_id: str) -> None:
        self._conn.execute(
            "UPDATE credentials SET last_verified_at=?, failed_logins=0, locked_until=0"
            " WHERE user_id=?",
            (self._now(), user_id),
        )
        self._conn.commit()

    def set_force_reset(self, user_id: str, force: bool = True) -> None:
        self._conn.execute(
            "UPDATE credentials SET force_reset=?, updated_at=? WHERE user_id=?",
            (1 if force else 0, self._now(), user_id),
        )
        self._conn.commit()

    def save_recovery_code(self, user_id: str, code_hash: str, *, ttl_sec: float = 86400) -> None:
        now = self._now()
        self._conn.execute(
            "INSERT INTO recovery_codes (code_hash, user_id, label, created_at, expires_at, used)"
            " VALUES (?,?,?,?,?,0)",
            (code_hash, user_id, "PRIVATE_ALPHA_ONLY", now, now + float(ttl_sec)),
        )
        self._conn.commit()

    def consume_recovery_code(self, code_hash: str) -> str | None:
        now = self._now()
        row = self._conn.execute(
            "SELECT * FROM recovery_codes WHERE code_hash=? AND used=0 AND expires_at > ?",
            (code_hash, now),
        ).fetchone()
        if not row:
            return None
        self._conn.execute(
            "UPDATE recovery_codes SET used=1 WHERE code_hash=?", (code_hash,)
        )
        self._conn.commit()
        return row["user_id"]

    # ── M51 invitations ───────────────────────────────────────────────────
    def create_invitation(
        self,
        *,
        org_id: str,
        email: str,
        role: str,
        inviter_id: str,
        token_hash: str,
        workspace_id: str = "",
        ttl_sec: float = 604800,
        invite_id: str = "",
    ) -> dict:
        iid = invite_id or new_id("inv_")
        now = self._now()
        exp = now + float(ttl_sec)
        self._conn.execute(
            "INSERT INTO invitations (invite_id, org_id, workspace_id, email, role, inviter_id,"
            " token_hash, status, created_at, expires_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                iid,
                org_id,
                workspace_id,
                email.lower().strip(),
                role,
                inviter_id,
                token_hash,
                "pending",
                now,
                exp,
            ),
        )
        self._conn.commit()
        return {
            "invite_id": iid,
            "org_id": org_id,
            "workspace_id": workspace_id,
            "email": email.lower().strip(),
            "role": role,
            "status": "pending",
            "expires_at": exp,
            "created_at": now,
        }

    def get_invitation_by_token_hash(self, token_hash: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM invitations WHERE token_hash=?", (token_hash,)
        ).fetchone()
        return dict(row) if row else None

    def get_invitation(self, invite_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM invitations WHERE invite_id=?", (invite_id,)
        ).fetchone()
        return dict(row) if row else None

    def update_invitation_status(
        self,
        invite_id: str,
        status: str,
        *,
        accepted_user_id: str = "",
    ) -> bool:
        now = self._now()
        cur = self._conn.execute(
            "UPDATE invitations SET status=?, accepted_at=?, accepted_user_id=? WHERE invite_id=?",
            (status, now if status == "accepted" else 0, accepted_user_id, invite_id),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def list_invitations(self, org_id: str, *, status: str = "") -> list[dict]:
        if status:
            rows = self._conn.execute(
                "SELECT * FROM invitations WHERE org_id=? AND status=? ORDER BY created_at DESC",
                (org_id, status),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM invitations WHERE org_id=? ORDER BY created_at DESC",
                (org_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    # ── M51 membership admin ──────────────────────────────────────────────
    def list_members(self, org_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT m.org_id, m.user_id, m.role, m.created_at,"
            " COALESCE(m.status, 'active') AS status, u.email, u.name"
            " FROM memberships m LEFT JOIN users u ON u.user_id=m.user_id"
            " WHERE m.org_id=? ORDER BY m.created_at",
            (org_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def set_member_role(self, org_id: str, user_id: str, role: str) -> bool:
        cur = self._conn.execute(
            "UPDATE memberships SET role=? WHERE org_id=? AND user_id=?",
            (role, org_id, user_id),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def set_member_status(self, org_id: str, user_id: str, status: str) -> bool:
        cur = self._conn.execute(
            "UPDATE memberships SET status=? WHERE org_id=? AND user_id=?",
            (status, org_id, user_id),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def remove_member(self, org_id: str, user_id: str) -> bool:
        cur = self._conn.execute(
            "DELETE FROM memberships WHERE org_id=? AND user_id=?",
            (org_id, user_id),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def count_owners(self, org_id: str) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM memberships WHERE org_id=? AND role='owner'"
            " AND COALESCE(status,'active')='active'",
            (org_id,),
        ).fetchone()
        return int(row["n"] if row else 0)

    def membership_role(self, org_id: str, user_id: str) -> str | None:
        row = self._conn.execute(
            "SELECT role, COALESCE(status,'active') AS status FROM memberships"
            " WHERE org_id=? AND user_id=?",
            (org_id, user_id),
        ).fetchone()
        if not row:
            return None
        if row["status"] != "active":
            return None
        return row["role"]

    # ── M51 rate limits ───────────────────────────────────────────────────
    def get_rate_limit(self, surface: str, key: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM rate_limits WHERE surface=? AND key=?", (surface, key)
        ).fetchone()
        return dict(row) if row else None

    def put_rate_limit(self, row: dict) -> None:
        self._conn.execute(
            "INSERT INTO rate_limits (surface, key, failures, window_start, locked_until)"
            " VALUES (?,?,?,?,?)"
            " ON CONFLICT(surface, key) DO UPDATE SET failures=excluded.failures,"
            " window_start=excluded.window_start, locked_until=excluded.locked_until",
            (
                row["surface"],
                row["key"],
                int(row.get("failures") or 0),
                float(row.get("window_start") or 0),
                float(row.get("locked_until") or 0),
            ),
        )
        self._conn.commit()

    def clear_rate_limit(self, surface: str, key: str) -> None:
        self._conn.execute(
            "DELETE FROM rate_limits WHERE surface=? AND key=?", (surface, key)
        )
        self._conn.commit()

    # ── M51 mission legacy link ───────────────────────────────────────────
    def link_legacy_mission(
        self, mission_id: str, legacy_key: str, org_id: str, workspace_id: str
    ) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO mission_legacy_links"
            " (mission_id, legacy_mission_key, org_id, workspace_id, created_at)"
            " VALUES (?,?,?,?,?)",
            (mission_id, legacy_key, org_id, workspace_id, self._now()),
        )
        self._conn.commit()

    def get_legacy_mission_links(self, org_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM mission_legacy_links WHERE org_id=?", (org_id,)
        ).fetchall()
        return [dict(r) for r in rows]
