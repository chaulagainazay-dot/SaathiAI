"""Security Store — the SQLite-native persistence layer for Authentication v1.2.

Replaces all JSON file stores (sessions.json, passkeys.json, reset_tokens.json,
audit.log) with a single SQLite database. Designed for PostgreSQL migration later
via adapter pattern — all SQL is standard, no SQLite-specific extensions.

Single-owner today; multi-user tomorrow. Every table has user_id so the schema
never needs changing when users are added.
"""
from __future__ import annotations

import json
import os
import secrets
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Callable


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

    # Operators (and the test suite) can redirect the default store away from the
    # real home directory. An explicit ``db_path`` still wins; when neither is
    # given the historical ``~/.saathi/security.db`` default is unchanged.
    _ENV_DB_PATH = "SAATHI_SECURITY_DB"

    def __init__(self, db_path: "str | Path | None" = None,
                 now: Callable[[], float] = time.time):
        if db_path:
            self.path = Path(db_path)
        else:
            override = os.environ.get(self._ENV_DB_PATH, "").strip()
            self.path = Path(override) if override else (Path.home() / ".saathi" / "security.db")
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
        """Return the owner user_id. Creates if absent."""
        row = self.db.execute("SELECT id FROM users WHERE status='active' LIMIT 1").fetchone()
        if row:
            return row["id"]
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

    def active_owner_has_password(self) -> bool:
        """Return whether an active canonical owner has a stored password.

        This deliberately returns only a boolean so callers such as the unlock
        status endpoint never need to handle credential material.
        """
        row = self.db.execute(
            "SELECT 1 FROM users u JOIN passwords p ON p.user_id=u.id "
            "WHERE u.status='active' LIMIT 1"
        ).fetchone()
        return row is not None

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
        """One-time migration from JSON files to SQLite. Idempotent."""
        migrated = {"sessions": 0, "passkeys": 0, "reset_tokens": 0, "audit": 0}

        # Ensure owner exists
        owner_id = self.get_or_create_owner()

        # Sessions
        legacy_sessions = Path.home() / ".saathi" / "sessions.json"
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
        legacy_passkeys = Path.home() / ".saathi" / "passkeys.json"
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
        legacy_reset = Path.home() / ".saathi" / "reset_tokens.json"
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
        legacy_audit = Path.home() / ".saathi" / "auth_audit.log"
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
