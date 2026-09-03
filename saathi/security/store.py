"""Security Store — the SQLite-native persistence layer for Authentication v1.2.

Replaces all JSON file stores (sessions.json, passkeys.json, reset_tokens.json,
audit.log) with a single SQLite database. Designed for PostgreSQL migration later
via adapter pattern — all SQL is standard, no SQLite-specific extensions.

Single-owner today; multi-user tomorrow. Every table has user_id so the schema
never needs changing when users are added.
"""
from __future__ import annotations

import json
import secrets
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Callable

from saathi.runtime_paths import state_path


# ── schema ───────────────────────────────────────────────────────────────────
_SCHEMA = """
-- Users — single owner today; multi-user tomorrow
CREATE TABLE IF NOT EXISTS users (
    id          TEXT PRIMARY KEY,
    email       TEXT UNIQUE,
    name        TEXT,
    avatar_url  TEXT,
    status      TEXT DEFAULT 'active',
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL
);

-- Password history
CREATE TABLE IF NOT EXISTS passwords (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         TEXT NOT NULL,
    hash            TEXT NOT NULL,
    strength_score  INTEGER DEFAULT 0,
    created_at      REAL NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Sessions — replaces sessions.json
CREATE TABLE IF NOT EXISTS sessions (
    id              TEXT PRIMARY KEY,
    token_hash      TEXT NOT NULL UNIQUE,
    user_id         TEXT NOT NULL,
    browser         TEXT DEFAULT 'Unknown',
    os              TEXT DEFAULT 'Unknown',
    platform        TEXT DEFAULT 'Unknown',
    device_name     TEXT DEFAULT 'Unknown',
    user_agent      TEXT,
    ip_address      TEXT,
    country         TEXT,
    timezone        TEXT,
    language        TEXT,
    login_method    TEXT DEFAULT 'password',
    first_seen      REAL NOT NULL,
    last_seen       REAL NOT NULL,
    revoked         INTEGER DEFAULT 0,
    expires_at      REAL NOT NULL,
    remember_me     INTEGER DEFAULT 1,
    risk_score      INTEGER DEFAULT 0,
    label           TEXT DEFAULT '',
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Passkeys — replaces passkeys.json
CREATE TABLE IF NOT EXISTS passkeys (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    public_key      TEXT NOT NULL,
    sign_count      INTEGER DEFAULT 0,
    rp_id           TEXT NOT NULL,
    device_name     TEXT DEFAULT 'Unknown',
    browser         TEXT DEFAULT 'Unknown',
    platform        TEXT DEFAULT 'Unknown',
    created_at      REAL NOT NULL,
    last_used_at    REAL DEFAULT 0,
    label           TEXT DEFAULT '',
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Reset tokens — replaces reset_tokens.json
CREATE TABLE IF NOT EXISTS reset_tokens (
    token       TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    email       TEXT,
    created_at  REAL NOT NULL,
    expires_at  REAL NOT NULL,
    used        INTEGER DEFAULT 0,
    ip_address  TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- API Tokens — replaces SAATHI_TOKEN global
CREATE TABLE IF NOT EXISTS api_tokens (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    name            TEXT NOT NULL,
    purpose         TEXT,
    token_hash      TEXT NOT NULL UNIQUE,
    permissions     TEXT DEFAULT '[]',
    created_at      REAL NOT NULL,
    expires_at      REAL,
    last_used_at    REAL DEFAULT 0,
    revoked         INTEGER DEFAULT 0,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- OAuth identities
CREATE TABLE IF NOT EXISTS oauth_identities (
    id                  TEXT PRIMARY KEY,
    user_id             TEXT NOT NULL,
    provider            TEXT NOT NULL,
    provider_user_id    TEXT NOT NULL,
    email               TEXT,
    name                TEXT,
    access_token        TEXT,
    refresh_token       TEXT,
    expires_at          REAL,
    created_at          REAL NOT NULL,
    last_used_at        REAL DEFAULT 0,
    UNIQUE (provider, provider_user_id),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Security Timeline — append-only
CREATE TABLE IF NOT EXISTS security_events (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    timestamp   REAL NOT NULL,
    kind        TEXT NOT NULL,
    title       TEXT NOT NULL,
    detail      TEXT,
    meta        TEXT DEFAULT '{}',
    ip_address  TEXT,
    user_agent  TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Audit log — replaces auth_audit.log
CREATE TABLE IF NOT EXISTS audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   REAL NOT NULL,
    event       TEXT NOT NULL,
    ok          INTEGER DEFAULT 1,
    user_id     TEXT,
    ip_address  TEXT,
    user_agent  TEXT,
    detail      TEXT,
    session_id  TEXT
);

-- D14: first-owner bootstrap marker. One row, id=1, written inside the same
-- transaction that creates the owner and its credential. Its presence is what
-- makes bootstrap permanently unavailable, including across restarts -- a
-- process-global flag would re-arm on every boot.
CREATE TABLE IF NOT EXISTS bootstrap_marker (
    id           INTEGER PRIMARY KEY CHECK (id = 1),
    completed_at REAL NOT NULL,
    owner_id     TEXT NOT NULL,
    method       TEXT NOT NULL
);

-- Multi-user foundation (stubs)
CREATE TABLE IF NOT EXISTS organizations (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    owner_id    TEXT NOT NULL,
    created_at  REAL NOT NULL,
    FOREIGN KEY (owner_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS teams (
    id          TEXT PRIMARY KEY,
    org_id      TEXT NOT NULL,
    name        TEXT NOT NULL,
    created_at  REAL NOT NULL,
    FOREIGN KEY (org_id) REFERENCES organizations(id)
);

CREATE TABLE IF NOT EXISTS team_members (
    team_id     TEXT NOT NULL,
    user_id     TEXT NOT NULL,
    role        TEXT DEFAULT 'member',
    joined_at   REAL NOT NULL,
    PRIMARY KEY (team_id, user_id),
    FOREIGN KEY (team_id) REFERENCES teams(id),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS roles (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    permissions TEXT NOT NULL DEFAULT '[]',
    created_at  REAL NOT NULL
);

-- Phase 18: durable authority delegation.
--
-- Answers, for work that outlives the request that started it: who authorized
-- it, what exactly they delegated, to which run or job, for how long, and up to
-- what authority. It lives here because this store already owns identity and
-- RBAC, so the origin user and their current permissions are checked against
-- the same database that issued them.
--
-- Deliberately NOT here: any session token, cookie or header. A session is
-- authentication material and re-presenting one later is impersonation, not
-- delegation. This record carries identity and scope, never a reusable secret.
--
-- Distinct from `delegation` in the agent-runtime store, which is agent-to-agent
-- operational hand-off (parent_agent -> child_agent). Same word, different
-- thing: that one moves work between agents, this one carries a *user's*
-- authority across time. Conflating them is how an agent would appear to hold
-- authority a user never granted.
CREATE TABLE IF NOT EXISTS authority_delegation (
    delegation_id     TEXT PRIMARY KEY,
    user_id           TEXT NOT NULL,
    scope_kind        TEXT NOT NULL,
    scope_ref         TEXT NOT NULL,
    action            TEXT NOT NULL,
    authority_ceiling TEXT NOT NULL,
    created_at        REAL NOT NULL,
    expires_at        REAL NOT NULL,
    max_uses          INTEGER NOT NULL DEFAULT 1,
    used              INTEGER NOT NULL DEFAULT 0,
    revoked_at        REAL,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS user_roles (
    user_id     TEXT NOT NULL,
    role_id     TEXT NOT NULL,
    org_id      TEXT,
    assigned_at REAL NOT NULL,
    PRIMARY KEY (user_id, role_id, org_id),
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (role_id) REFERENCES roles(id),
    FOREIGN KEY (org_id) REFERENCES organizations(id)
);

-- Default roles
INSERT OR IGNORE INTO roles (id, name, permissions, created_at)
VALUES
    ('role-owner',  'Owner',  '["*"]', 1750963200),
    ('role-admin',  'Admin',  '["read","write","delete","invite"]', 1750963200),
    ('role-member', 'Member', '["read","write"]', 1750963200),
    ('role-viewer', 'Viewer', '["read"]', 1750963200);
"""

_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_deleg_user ON authority_delegation(user_id);
CREATE INDEX IF NOT EXISTS idx_deleg_scope ON authority_delegation(scope_kind, scope_ref);

CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id, last_seen DESC);
CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions(token_hash);
CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at);
CREATE INDEX IF NOT EXISTS idx_passkeys_user ON passkeys(user_id);
CREATE INDEX IF NOT EXISTS idx_api_tokens_hash ON api_tokens(token_hash);
CREATE INDEX IF NOT EXISTS idx_api_tokens_user ON api_tokens(user_id, last_used_at DESC);
CREATE INDEX IF NOT EXISTS idx_oauth_provider ON oauth_identities(provider, provider_user_id);
CREATE INDEX IF NOT EXISTS idx_security_events_user ON security_events(user_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_security_events_kind ON security_events(kind, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_audit_event ON audit_log(event, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_log(user_id, timestamp DESC);
"""


class SecurityStore:
    """Central security persistence. SQLite today; PostgreSQL tomorrow via adapter.

    Thread-safe: uses check_same_thread=False. Callers must not share connections
    across threads without locks, but the store object itself is safe to use
    from the async event loop (single thread).
    """

    def __init__(self, db_path: "str | Path | None" = None,
                 now: Callable[[], float] = time.time):
        self.path = Path(db_path) if db_path else state_path("security.db")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._now = now
        self.db = sqlite3.connect(str(self.path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.executescript(_SCHEMA)
        self.db.executescript(_INDEXES)
        self.db.commit()

    # ── users ────────────────────────────────────────────────────────────────
    def get_or_create_owner(self, email: str = "", name: str = "") -> str:
        """Return the owner user_id, creating it only on a bootstrapped system.

        D14: creating an owner is bootstrap's job and nobody else's. This method
        used to manufacture one on demand, and every caller of it -- including
        ``has_passkey``, reached by the public unlock screen -- therefore wrote a
        users row into an uninitialised store. That row is itself the evidence
        ``auth_state`` reads to detect planting, so a fresh install answered one
        anonymous GET and then classified itself CONTAMINATED_UNINITIALIZED,
        refusing the bootstrap it had never had. The creating branch is now
        conditional on the bootstrap marker; before that, callers get "".
        """
        row = self.db.execute("SELECT id FROM users WHERE status='active' LIMIT 1").fetchone()
        if row:
            return row["id"]
        if not self.bootstrap_completed():
            return ""
        uid = uuid.uuid4().hex
        now = self._now()
        self.db.execute(
            "INSERT INTO users (id, email, name, created_at, updated_at) VALUES (?,?,?,?,?)",
            (uid, email or None, name or None, now, now),
        )
        # Assign owner role
        self.db.execute(
            "INSERT OR IGNORE INTO user_roles (user_id, role_id, assigned_at) VALUES (?,?,?)",
            (uid, "role-owner", now),
        )
        self.db.commit()
        return uid

    def owner_id(self) -> str | None:
        """The owner user_id, or None. Never creates.

        ``get_or_create_owner`` is unusable for an authentication decision: it
        manufactures the very identity the caller is asking about, which is how
        an unauthenticated caller came to own a freshly installed system.
        """
        row = self.db.execute(
            "SELECT id FROM users WHERE status='active' ORDER BY created_at LIMIT 1"
        ).fetchone()
        return row["id"] if row else None

    def bootstrap_completed(self) -> dict | None:
        row = self.db.execute("SELECT * FROM bootstrap_marker WHERE id=1").fetchone()
        return dict(row) if row else None

    def credential_census(self) -> dict[str, int]:
        """Count every durable authentication artefact this store holds.

        Used to tell an untouched installation apart from one where something
        has already planted a credential. Counting is read-only and creates
        nothing.
        """
        def n(sql: str) -> int:
            return int(self.db.execute(sql).fetchone()[0])

        return {
            "users":     n("SELECT COUNT(*) FROM users"),
            "passwords": n("SELECT COUNT(*) FROM passwords"),
            "sessions":  n("SELECT COUNT(*) FROM sessions"),
            "api_tokens": n("SELECT COUNT(*) FROM api_tokens"),
            "passkeys":  n("SELECT COUNT(*) FROM passkeys"),
            "user_roles": n("SELECT COUNT(*) FROM user_roles"),
        }

    def get_user(self, user_id: str) -> dict | None:
        row = self.db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        return dict(row) if row else None

    # ── passwords ────────────────────────────────────────────────────────────
    def save_password(self, user_id: str, hash_: str, strength_score: int = 0) -> int:
        cur = self.db.execute(
            "INSERT INTO passwords (user_id, hash, strength_score, created_at) VALUES (?,?,?,?)",
            (user_id, hash_, strength_score, self._now()),
        )
        self.db.commit()
        return cur.lastrowid

    def latest_password(self, user_id: str) -> dict | None:
        row = self.db.execute(
            "SELECT * FROM passwords WHERE user_id=? ORDER BY created_at DESC LIMIT 1",
            (user_id,),
        ).fetchone()
        return dict(row) if row else None

    def has_password(self, user_id: str) -> bool:
        """Whether a stored password credential exists for ``user_id``.

        The presence question and the credential itself are different facts.
        ``latest_password`` answers the second and hands the caller a hash, so
        a surface that only needs the first had to fetch a secret to discard
        it. This answers the first alone: the row is counted in SQL and the
        hash never leaves the database.
        """
        row = self.db.execute(
            "SELECT 1 FROM passwords WHERE user_id=? AND LENGTH(hash) > 0 LIMIT 1",
            (user_id,),
        ).fetchone()
        return row is not None

    def owner_has_password(self) -> bool:
        """Whether the active canonical owner has a stored password credential.

        Returns False when there is no owner at all, which is what an
        uninitialised installation looks like from here. Creates nothing.
        """
        owner = self.owner_id()
        return bool(owner) and self.has_password(owner)

    def password_history(self, user_id: str, limit: int = 10) -> list[dict]:
        rows = self.db.execute(
            "SELECT * FROM passwords WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── sessions ─────────────────────────────────────────────────────────────
    def session_create(self, user_id: str, token_hash: str, **fields) -> None:
        now = self._now()
        sid = token_hash[:12]
        defaults = {
            "id": sid, "token_hash": token_hash, "user_id": user_id,
            "first_seen": now, "last_seen": now,
            "browser": "Unknown", "os": "Unknown", "platform": "Unknown",
            "device_name": "Unknown", "user_agent": "", "ip_address": "",
            "login_method": "password", "revoked": 0,
            "expires_at": now + 30 * 24 * 3600, "remember_me": 1,
            "risk_score": 0, "label": "",
        }
        defaults.update(fields)
        cols = ",".join(defaults.keys())
        ph = ",".join("?" * len(defaults))
        self.db.execute(f"INSERT INTO sessions ({cols}) VALUES ({ph})", tuple(defaults.values()))
        self.db.commit()

    def session_by_hash(self, token_hash: str) -> dict | None:
        row = self.db.execute(
            "SELECT * FROM sessions WHERE token_hash=? AND revoked=0", (token_hash,)
        ).fetchone()
        return dict(row) if row else None

    def session_touch(self, token_hash: str) -> None:
        self.db.execute("UPDATE sessions SET last_seen=? WHERE token_hash=?",
                        (self._now(), token_hash))
        self.db.commit()

    def session_revoke(self, session_id: str) -> bool:
        cur = self.db.execute("UPDATE sessions SET revoked=1 WHERE id=?", (session_id,))
        self.db.commit()
        return cur.rowcount > 0

    def session_revoke_all(self, user_id: str, except_hash: str = "") -> int:
        sql = "UPDATE sessions SET revoked=1 WHERE user_id=? AND revoked=0"
        args: list = [user_id]
        if except_hash:
            sql += " AND token_hash != ?"
            args.append(except_hash)
        cur = self.db.execute(sql, args)
        self.db.commit()
        return cur.rowcount

    def session_list(self, user_id: str) -> list[dict]:
        now = self._now()
        rows = self.db.execute(
            "SELECT * FROM sessions WHERE user_id=? AND revoked=0 AND expires_at > ?"
            " ORDER BY last_seen DESC",
            (user_id, now),
        ).fetchall()
        return [dict(r) for r in rows]

    def session_prune_expired(self, user_id: str) -> int:
        """Hard-delete expired sessions. Returns count deleted."""
        cur = self.db.execute(
            "DELETE FROM sessions WHERE user_id=? AND expires_at <= ?",
            (user_id, self._now()),
        )
        self.db.commit()
        return cur.rowcount

    def session_rename(self, session_id: str, label: str) -> bool:
        cur = self.db.execute("UPDATE sessions SET label=? WHERE id=?",
                              (label[:60], session_id))
        self.db.commit()
        return cur.rowcount > 0

    # ── passkeys ─────────────────────────────────────────────────────────────
    def passkey_save(self, user_id: str, credential_id: str, public_key: str,
                     rp_id: str, **fields) -> None:
        now = self._now()
        defaults = {
            "id": credential_id, "user_id": user_id, "public_key": public_key,
            "rp_id": rp_id, "sign_count": 0, "device_name": "Unknown",
            "browser": "Unknown", "platform": "Unknown",
            "created_at": now, "last_used_at": 0, "label": "",
        }
        defaults.update(fields)
        cols = ",".join(defaults.keys())
        ph = ",".join("?" * len(defaults))
        self.db.execute(f"INSERT INTO passkeys ({cols}) VALUES ({ph})", tuple(defaults.values()))
        self.db.commit()

    def passkey_list(self, user_id: str, rp_id: str = "") -> list[dict]:
        sql = "SELECT * FROM passkeys WHERE user_id=?"
        args: list = [user_id]
        if rp_id:
            sql += " AND rp_id=?"
            args.append(rp_id)
        rows = self.db.execute(sql, args).fetchall()
        return [dict(r) for r in rows]

    def passkey_get(self, credential_id: str) -> dict | None:
        row = self.db.execute("SELECT * FROM passkeys WHERE id=?", (credential_id,)).fetchone()
        return dict(row) if row else None

    def passkey_update_sign_count(self, credential_id: str, sign_count: int) -> None:
        self.db.execute(
            "UPDATE passkeys SET sign_count=?, last_used_at=? WHERE id=?",
            (sign_count, self._now(), credential_id),
        )
        self.db.commit()

    def passkey_delete(self, credential_id: str) -> bool:
        cur = self.db.execute("DELETE FROM passkeys WHERE id=?", (credential_id,))
        self.db.commit()
        return cur.rowcount > 0

    def passkey_rename(self, credential_id: str, label: str) -> bool:
        cur = self.db.execute("UPDATE passkeys SET label=? WHERE id=?",
                              (label[:60], credential_id))
        self.db.commit()
        return cur.rowcount > 0

    # ── reset tokens ─────────────────────────────────────────────────────────
    def reset_token_create(self, user_id: str, token: str, email: str = "",
                           expires_at: float | None = None, ip: str = "") -> None:
        now = self._now()
        self.db.execute(
            "INSERT INTO reset_tokens (token, user_id, email, created_at, expires_at, ip_address)"
            " VALUES (?,?,?,?,?,?)",
            (token, user_id, email or None, now, expires_at or (now + 900), ip),
        )
        self.db.commit()

    def reset_token_get(self, token: str) -> dict | None:
        row = self.db.execute(
            "SELECT * FROM reset_tokens WHERE token=? AND used=0 AND expires_at > ?",
            (token, self._now()),
        ).fetchone()
        return dict(row) if row else None

    def reset_token_mark_used(self, token: str) -> bool:
        cur = self.db.execute("UPDATE reset_tokens SET used=1 WHERE token=?", (token,))
        self.db.commit()
        return cur.rowcount > 0

    def reset_token_prune(self) -> int:
        cur = self.db.execute("DELETE FROM reset_tokens WHERE expires_at <= ?", (self._now(),))
        self.db.commit()
        return cur.rowcount

    # ── api tokens ───────────────────────────────────────────────────────────
    def api_token_create(self, user_id: str, name: str, token_hash: str,
                         purpose: str = "", permissions: list[str] | None = None,
                         expires_at: float | None = None) -> str:
        tid = uuid.uuid4().hex
        self.db.execute(
            "INSERT INTO api_tokens (id, user_id, name, purpose, token_hash, permissions,"
            " created_at, expires_at) VALUES (?,?,?,?,?,?,?,?)",
            (tid, user_id, name, purpose or None, token_hash,
             json.dumps(permissions or []), self._now(), expires_at),
        )
        self.db.commit()
        return tid

    def api_token_by_hash(self, token_hash: str) -> dict | None:
        row = self.db.execute(
            "SELECT * FROM api_tokens WHERE token_hash=? AND revoked=0"
            " AND (expires_at IS NULL OR expires_at > ?)",
            (token_hash, self._now()),
        ).fetchone()
        return dict(row) if row else None

    def api_token_touch(self, token_id: str) -> None:
        self.db.execute("UPDATE api_tokens SET last_used_at=? WHERE id=?",
                        (self._now(), token_id))
        self.db.commit()

    def api_token_list(self, user_id: str) -> list[dict]:
        rows = self.db.execute(
            "SELECT id, name, purpose, permissions, created_at, expires_at,"
            " last_used_at, revoked FROM api_tokens WHERE user_id=? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            try:
                d["permissions"] = json.loads(d.get("permissions") or "[]")
            except Exception:
                d["permissions"] = []
            out.append(d)
        return out

    def api_token_revoke(self, token_id: str) -> bool:
        cur = self.db.execute("UPDATE api_tokens SET revoked=1 WHERE id=?", (token_id,))
        self.db.commit()
        return cur.rowcount > 0

    # ── oauth identities ─────────────────────────────────────────────────────
    def oauth_save(self, user_id: str, provider: str, provider_user_id: str,
                   email: str = "", name: str = "", access_token: str = "",
                   refresh_token: str = "", expires_at: float | None = None) -> str:
        now = self._now()
        # Upsert
        existing = self.db.execute(
            "SELECT id FROM oauth_identities WHERE provider=? AND provider_user_id=?",
            (provider, provider_user_id),
        ).fetchone()
        if existing:
            self.db.execute(
                "UPDATE oauth_identities SET access_token=?, refresh_token=?,"
                " expires_at=?, last_used_at=? WHERE id=?",
                (access_token or None, refresh_token or None, expires_at, now, existing["id"]),
            )
            self.db.commit()
            return existing["id"]
        oid = uuid.uuid4().hex
        self.db.execute(
            "INSERT INTO oauth_identities (id, user_id, provider, provider_user_id,"
            " email, name, access_token, refresh_token, expires_at, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (oid, user_id, provider, provider_user_id, email or None, name or None,
             access_token or None, refresh_token or None, expires_at, now),
        )
        self.db.commit()
        return oid

    def oauth_list(self, user_id: str) -> list[dict]:
        rows = self.db.execute(
            "SELECT id, provider, provider_user_id, email, name, created_at, last_used_at"
            " FROM oauth_identities WHERE user_id=?",
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── security events (timeline) ───────────────────────────────────────────
    def event_record(self, user_id: str, kind: str, title: str, *, detail: str = "",
                     meta: dict | None = None, ip: str = "", ua: str = "") -> str:
        eid = uuid.uuid4().hex[:16]
        self.db.execute(
            "INSERT INTO security_events (id, user_id, timestamp, kind, title, detail, meta,"
            " ip_address, user_agent) VALUES (?,?,?,?,?,?,?,?,?)",
            (eid, user_id, self._now(), kind, title, detail, json.dumps(meta or {}),
             ip or None, ua or None),
        )
        self.db.commit()
        return eid

    def event_list(self, user_id: str, *, kind: str | None = None, limit: int = 100) -> list[dict]:
        sql = "SELECT * FROM security_events WHERE user_id=?"
        args: list = [user_id]
        if kind:
            sql += " AND kind=?"
            args.append(kind)
        sql += " ORDER BY timestamp DESC LIMIT ?"
        args.append(limit)
        rows = self.db.execute(sql, args).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            try:
                d["meta"] = json.loads(d.get("meta") or "{}")
            except Exception:
                d["meta"] = {}
            out.append(d)
        return out

    # ── audit log ────────────────────────────────────────────────────────────
    # ── authorization ─────────────────────────────────────────────────────

    def permissions_for(self, user_id: str) -> set[str]:
        """Every permission this user holds, unioned across their roles.

        The roles and their permissions have existed since the security store
        was introduced; nothing consulted them. Returns an empty set for an
        unknown user, so an unrecognised caller is authorised for nothing.
        """
        if not user_id:
            return set()
        rows = self.db.execute(
            "SELECT r.permissions FROM user_roles ur "
            "JOIN roles r ON r.id = ur.role_id WHERE ur.user_id = ?",
            (user_id,),
        ).fetchall()
        out: set[str] = set()
        for row in rows:
            try:
                out.update(json.loads(row["permissions"] or "[]"))
            except (ValueError, TypeError):
                continue
        return out

    def has_permission(self, user_id: str, permission: str) -> bool:
        """Whether the user may do `permission`. ``*`` grants everything.

        Fails closed: no user, no roles, or an unparsable permission list all
        answer no.
        """
        if not user_id or not permission:
            return False
        held = self.permissions_for(user_id)
        return "*" in held or permission in held

    # ── authority delegation (Phase 18) ──────────────────────────────────────
    #: Serialises the delegation mutators. The store shares one sqlite
    #: connection across threads (`check_same_thread=False`), which is fine for
    #: the request-per-thread paths that reach it one at a time, but delegated
    #: workers race for the same one-shot record by design. Without this, two
    #: workers issuing UPDATEs on the same connection misuse the driver rather
    #: than contending on the row. Scoped to these methods rather than the whole
    #: store: widening it is a separate change with its own evidence.
    _delegation_lock = threading.RLock()

    def delegation_lock(self):
        """The lock guarding a delegation's validate-then-claim sequence.

        Exposed because the invariant spans more than one store call. Locking
        only the mutators was not enough: the reads that validate a delegation
        run on the same shared connection, so a worker could read a live record
        while another was claiming it and both would proceed. Callers hold this
        across the whole read-check-claim sequence.

        Reentrant, so the mutators can take it again inside a held section.
        """
        return self._delegation_lock

    def create_delegation(self, *, user_id: str, scope_kind: str, scope_ref: str,
                          action: str, authority_ceiling: str, ttl_sec: float,
                          max_uses: int = 1) -> str:
        """Record that `user_id` delegated one bounded action to deferred work.

        The caller supplies the user id from server-resolved identity; this
        method neither reads a request nor accepts a claim. Nothing stored here
        is reusable as a credential.
        """
        import uuid

        delegation_id = f"dlg_{uuid.uuid4().hex[:24]}"
        now = self._now()
        self.db.execute(
            "INSERT INTO authority_delegation (delegation_id, user_id, scope_kind,"
            " scope_ref, action, authority_ceiling, created_at, expires_at,"
            " max_uses, used, revoked_at) VALUES (?,?,?,?,?,?,?,?,?,0,NULL)",
            (delegation_id, user_id, scope_kind, scope_ref, action,
             authority_ceiling, now, now + float(ttl_sec), int(max_uses)),
        )
        self.db.commit()
        return delegation_id

    def get_delegation(self, delegation_id: str) -> dict | None:
        row = self.db.execute(
            "SELECT * FROM authority_delegation WHERE delegation_id=?",
            (delegation_id,),
        ).fetchone()
        return dict(row) if row else None

    def consume_delegation(self, delegation_id: str) -> bool:
        """Claim one use, atomically. True only for the caller that won it.

        The guard lives in the UPDATE's WHERE clause rather than in a read
        followed by a write, so two workers racing for the last use of a
        one-shot delegation cannot both observe `used < max_uses` and both
        proceed.
        """
        with self._delegation_lock:
            cur = self.db.execute(
                "UPDATE authority_delegation SET used = used + 1 "
                "WHERE delegation_id = ? AND used < max_uses AND revoked_at IS NULL",
                (delegation_id,),
            )
            self.db.commit()
            return cur.rowcount == 1

    def revoke_delegation(self, delegation_id: str) -> bool:
        with self._delegation_lock:
            cur = self.db.execute(
                "UPDATE authority_delegation SET revoked_at = ? "
                "WHERE delegation_id = ? AND revoked_at IS NULL",
                (self._now(), delegation_id),
            )
            self.db.commit()
            return cur.rowcount == 1

    def revoke_delegations_for_scope(self, scope_kind: str, scope_ref: str) -> int:
        """Revoke every live delegation bound to one run or job.

        Cancelling the parent work is the natural revocation gesture: a
        delegation exists to authorize *that* work, so it should not outlive it.
        """
        cur = self.db.execute(
            "UPDATE authority_delegation SET revoked_at = ? "
            "WHERE scope_kind = ? AND scope_ref = ? AND revoked_at IS NULL",
            (self._now(), scope_kind, scope_ref),
        )
        self.db.commit()
        return cur.rowcount

    def audit(self, event: str, *, ok: bool = True, user_id: str = "", ip: str = "",
              ua: str = "", detail: str = "", session_id: str = "") -> None:
        self.db.execute(
            "INSERT INTO audit_log (timestamp, event, ok, user_id, ip_address, user_agent,"
            " detail, session_id) VALUES (?,?,?,?,?,?,?,?)",
            (self._now(), event, 1 if ok else 0, user_id or None, ip or None,
             ua or None, detail or None, session_id or None),
        )
        self.db.commit()

    def audit_recent(self, user_id: str = "", limit: int = 40) -> list[dict]:
        if user_id:
            rows = self.db.execute(
                "SELECT * FROM audit_log WHERE user_id=? ORDER BY timestamp DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
        else:
            rows = self.db.execute(
                "SELECT * FROM audit_log ORDER BY timestamp DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    # ── migration from legacy JSON files ─────────────────────────────────────
    def migrate_from_legacy(self) -> dict:
        """One-time migration from JSON files to SQLite. Idempotent.

        D14: refused before the system is bootstrapped. ``get_store()`` runs this
        on first access in every process, so on an uninitialised install it ran
        before anybody had authenticated -- creating an owner and importing
        legacy sessions and passkeys into a store with no owner behind them.
        That is credential planting performed by the server on its own behalf,
        and it left a fresh install unable to bootstrap at all. A legacy upgrade
        migrates on the first process that starts after its owner exists.
        """
        migrated = {"sessions": 0, "passkeys": 0, "reset_tokens": 0, "audit": 0}

        if not self.bootstrap_completed():
            migrated["skipped"] = "NOT_INITIALIZED"
            return migrated

        owner_id = self.get_or_create_owner()

        # Sessions
        legacy_sessions = state_path("sessions.json")
        if legacy_sessions.exists():
            try:
                rows = json.loads(legacy_sessions.read_text())
                for r in rows:
                    sid = r.get("id", "") or r.get("th", "")[:12]
                    self.db.execute(
                        """INSERT OR IGNORE INTO sessions
                        (id, token_hash, user_id, browser, os, platform, device_name,
                         user_agent, ip_address, login_method, first_seen, last_seen,
                         revoked, expires_at, remember_me, risk_score, label)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (sid, r.get("th", ""), owner_id, r.get("browser", "Unknown"),
                         r.get("os", "Unknown"), "Unknown", r.get("device_name", "Unknown"),
                         r.get("ua", "")[:200], r.get("ip", ""),
                         r.get("kind", "password"), r.get("created", 0),
                         r.get("last_seen", 0), 1 if r.get("revoked") else 0,
                         r.get("expires", 0), 1 if r.get("remember_me", True) else 0,
                         r.get("risk_score", 0), r.get("label", "")),
                    )
                    migrated["sessions"] += 1
                self.db.commit()
            except Exception:
                pass

        # Passkeys
        legacy_passkeys = state_path("passkeys.json")
        if legacy_passkeys.exists():
            try:
                rows = json.loads(legacy_passkeys.read_text())
                for r in rows:
                    self.db.execute(
                        """INSERT OR IGNORE INTO passkeys
                        (id, user_id, public_key, sign_count, rp_id, device_name,
                         browser, platform, created_at, last_used_at, label)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                        (r.get("id", ""), owner_id, r.get("public_key", ""),
                         r.get("sign_count", 0), r.get("rp_id", ""),
                         r.get("device_name", "Unknown"), r.get("browser", "Unknown"),
                         "Unknown", r.get("created", 0), r.get("last_used", 0),
                         r.get("label", "")),
                    )
                    migrated["passkeys"] += 1
                self.db.commit()
            except Exception:
                pass

        # Reset tokens
        legacy_reset = state_path("reset_tokens.json")
        if legacy_reset.exists():
            try:
                rows = json.loads(legacy_reset.read_text())
                for r in rows:
                    self.db.execute(
                        """INSERT OR IGNORE INTO reset_tokens
                        (token, user_id, email, created_at, expires_at, used, ip_address)
                        VALUES (?,?,?,?,?,?,?)""",
                        (r.get("token", ""), owner_id, r.get("email", None),
                         r.get("created", 0), r.get("expires", 0),
                         1 if r.get("used") else 0, r.get("ip", "")),
                    )
                    migrated["reset_tokens"] += 1
                self.db.commit()
            except Exception:
                pass

        # Audit log (line-delimited JSON)
        legacy_audit = state_path("auth_audit.log")
        if legacy_audit.exists():
            try:
                for line in legacy_audit.read_text().splitlines()[-1000:]:
                    rec = json.loads(line)
                    self.db.execute(
                        "INSERT INTO audit_log (timestamp, event, ok, ip_address, user_agent, detail)"
                        " VALUES (?,?,?,?,?,?)",
                        (rec.get("ts", 0), rec.get("event", ""),
                         1 if rec.get("ok", True) else 0,
                         rec.get("ip", "") or None, rec.get("ua", "")[:160] or None,
                         rec.get("detail", "")[:200] or None),
                    )
                    migrated["audit"] += 1
                self.db.commit()
            except Exception:
                pass

        return migrated

    def close(self) -> None:
        self.db.close()


# ── process-wide singleton ───────────────────────────────────────────────────
_default_store: SecurityStore | None = None


def get_store(db_path: "str | Path | None" = None) -> SecurityStore:
    global _default_store
    if _default_store is None:
        _default_store = SecurityStore(db_path)
        _default_store.migrate_from_legacy()
    return _default_store


def close_store() -> None:
    global _default_store
    if _default_store is not None:
        try:
            _default_store.db.close()
        except Exception:
            pass
        _default_store = None
