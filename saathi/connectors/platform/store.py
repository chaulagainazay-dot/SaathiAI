"""M15 connector platform durable store — data/connectors.db.

Persists connected accounts (connection state), credential references
(metadata only), executions, approvals (bound to input hash), webhook events
(dedup + replay window), sync jobs (checkpoints), rate-limit buckets, failures.
No raw secrets are ever stored here.
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent.parent.parent
DB_PATH = ROOT / "data" / "connectors.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS account(
  id TEXT PRIMARY KEY, connector_id TEXT, owner TEXT NOT NULL, label TEXT DEFAULT '',
  provider_account_id TEXT DEFAULT '', state TEXT NOT NULL, cred_ref_id TEXT DEFAULT '',
  project_scope TEXT DEFAULT '', enabled INTEGER DEFAULT 1, created_at REAL, updated_at REAL);
CREATE TABLE IF NOT EXISTS credential_ref(
  ref_id TEXT PRIMARY KEY, connector_id TEXT, scope TEXT, backend TEXT,
  backend_key TEXT, label TEXT DEFAULT '', granted_scopes TEXT DEFAULT '[]',
  status TEXT DEFAULT 'unverified', expiry REAL, last_verified REAL,
  rotation_required INTEGER DEFAULT 0, created_at REAL, updated_at REAL);
CREATE TABLE IF NOT EXISTS execution(
  id TEXT PRIMARY KEY, owner TEXT, connector_id TEXT, tool_id TEXT, capability_id TEXT,
  account_id TEXT DEFAULT '', status TEXT, input_hash TEXT DEFAULT '',
  idempotency_key TEXT DEFAULT '', risk INTEGER, evidence TEXT DEFAULT '[]',
  errors TEXT DEFAULT '[]', external_reference TEXT DEFAULT '', created_at REAL);
CREATE TABLE IF NOT EXISTS approval(
  id TEXT PRIMARY KEY, owner TEXT, connector_id TEXT, account_id TEXT, tool_id TEXT,
  capability_id TEXT, input_hash TEXT, risk INTEGER, environment TEXT DEFAULT 'local',
  target TEXT DEFAULT '', status TEXT DEFAULT 'pending', max_uses INTEGER DEFAULT 1,
  used INTEGER DEFAULT 0, expires_at REAL, created_at REAL, resolved_at REAL DEFAULT 0);
CREATE TABLE IF NOT EXISTS webhook_event(
  id TEXT PRIMARY KEY, connector_id TEXT, dedup_key TEXT, received_at REAL,
  event_ts REAL, normalized TEXT DEFAULT '{}', status TEXT DEFAULT 'accepted');
CREATE TABLE IF NOT EXISTS sync_job(
  id TEXT PRIMARY KEY, owner TEXT, connector_id TEXT, cursor TEXT DEFAULT '',
  page_token TEXT DEFAULT '', last_sync REAL DEFAULT 0, batch_size INTEGER DEFAULT 100,
  state TEXT DEFAULT 'idle', processed INTEGER DEFAULT 0, created_at REAL, updated_at REAL);
CREATE TABLE IF NOT EXISTS rate_bucket(
  bucket TEXT PRIMARY KEY, remaining INTEGER, limit_n INTEGER, reset_at REAL,
  updated_at REAL);
CREATE TABLE IF NOT EXISTS failure(
  id TEXT PRIMARY KEY, connector_id TEXT, tool_id TEXT, fingerprint TEXT,
  failure_class TEXT, created_at REAL);
CREATE INDEX IF NOT EXISTS idx_acct_owner ON account(owner, connector_id);
CREATE INDEX IF NOT EXISTS idx_exec_owner ON execution(owner, created_at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_wh_dedup ON webhook_event(dedup_key) WHERE dedup_key != '';
CREATE UNIQUE INDEX IF NOT EXISTS idx_exec_idem ON execution(idempotency_key) WHERE idempotency_key != '';
"""


def _now() -> float:
    return time.time()


def _id(p="x") -> str:
    return f"{p}_" + uuid.uuid4().hex[:14]


class ConnectorStore:
    def __init__(self, db_path=None):
        self.db_path = Path(db_path) if db_path else DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(_SCHEMA)

    def _conn(self):
        c = sqlite3.connect(str(self.db_path))
        c.row_factory = sqlite3.Row
        return c

    def event(self, name, payload):
        try:
            from saathi.events import bus
            bus.publish_sync(name, payload)
        except Exception:
            pass

    # ── accounts ──────────────────────────────────────────────────────────
    def add_account(self, *, owner, connector_id, label="", cred_ref_id="",
                    state="configured", project_scope=""):
        aid = _id("acct")
        now = _now()
        with self._conn() as c:
            c.execute("INSERT INTO account(id,connector_id,owner,label,state,cred_ref_id,"
                     "project_scope,enabled,created_at,updated_at) VALUES(?,?,?,?,?,?,?,1,?,?)",
                     (aid, connector_id, owner, label, state, cred_ref_id, project_scope, now, now))
        self.event("connector.account.created", {"connector": connector_id, "owner": owner})
        return aid

    def get_account(self, aid) -> Optional[dict]:
        with self._conn() as c:
            row = c.execute("SELECT * FROM account WHERE id=?", (aid,)).fetchone()
        return dict(row) if row else None

    def set_account_state(self, aid, state, *, enabled=None):
        sets, args = ["state=?", "updated_at=?"], [state, _now()]
        if enabled is not None:
            sets.append("enabled=?"); args.append(1 if enabled else 0)
        args.append(aid)
        with self._conn() as c:
            c.execute(f"UPDATE account SET {','.join(sets)} WHERE id=?", args)

    def list_accounts(self, owner, connector_id=None):
        q = "SELECT * FROM account WHERE owner=?"
        args = [owner]
        if connector_id:
            q += " AND connector_id=?"; args.append(connector_id)
        with self._conn() as c:
            return [dict(r) for r in c.execute(q, args).fetchall()]

    # ── credential refs (metadata only) ───────────────────────────────────
    def put_cred_ref(self, ref) -> str:
        d = ref.to_dict()
        with self._conn() as c:
            c.execute("INSERT OR REPLACE INTO credential_ref(ref_id,connector_id,scope,"
                     "backend,backend_key,label,granted_scopes,status,expiry,last_verified,"
                     "rotation_required,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (d["ref_id"], d["connector_id"], d["scope"], d["backend"],
                      d["backend_key"], d["label"], json.dumps(d.get("granted_scopes", [])),
                      d["status"], d.get("expiry"), d.get("last_verified"),
                      1 if d.get("rotation_required") else 0, d["created_at"], d["updated_at"]))
        return d["ref_id"]

    def get_cred_ref(self, ref_id) -> Optional[dict]:
        with self._conn() as c:
            row = c.execute("SELECT * FROM credential_ref WHERE ref_id=?", (ref_id,)).fetchone()
        return dict(row) if row else None

    def delete_cred_ref(self, ref_id):
        with self._conn() as c:
            c.execute("DELETE FROM credential_ref WHERE ref_id=?", (ref_id,))

    # ── executions ────────────────────────────────────────────────────────
    def record_execution(self, *, owner, result, risk, input_hash="", idempotency_key="",
                         account_id=""):
        eid = result.execution_id or _id("exec")
        with self._conn() as c:
            try:
                c.execute("INSERT INTO execution(id,owner,connector_id,tool_id,capability_id,"
                         "account_id,status,input_hash,idempotency_key,risk,evidence,errors,"
                         "external_reference,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                         (eid, owner, result.connector_id, result.tool_id, result.capability_id,
                          account_id, result.status, input_hash, idempotency_key, int(risk),
                          json.dumps(result.evidence), json.dumps(result.errors),
                          result.external_reference or "", _now()))
            except sqlite3.IntegrityError:
                pass  # idempotency duplicate
        return eid

    def execution_by_idempotency(self, key):
        if not key:
            return None
        with self._conn() as c:
            row = c.execute("SELECT * FROM execution WHERE idempotency_key=?", (key,)).fetchone()
        return dict(row) if row else None

    def list_executions(self, owner, limit=50, offset=0):
        with self._conn() as c:
            rows = c.execute("SELECT * FROM execution WHERE owner=? ORDER BY created_at DESC "
                            "LIMIT ? OFFSET ?", (owner, limit, offset)).fetchall()
        return [dict(r) for r in rows]

    # ── approvals (bound to input hash) ───────────────────────────────────
    def add_approval(self, *, owner, connector_id, account_id, tool_id, capability_id,
                    input_hash, risk, environment="local", target="", ttl_sec=3600,
                    max_uses=1):
        aid = _id("appr")
        now = _now()
        with self._conn() as c:
            c.execute("INSERT INTO approval(id,owner,connector_id,account_id,tool_id,"
                     "capability_id,input_hash,risk,environment,target,status,max_uses,used,"
                     "expires_at,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,0,?,?)",
                     (aid, owner, connector_id, account_id, tool_id, capability_id,
                      input_hash, int(risk), environment, target, "pending", max_uses,
                      now + ttl_sec, now))
        return aid

    def get_approval(self, aid):
        with self._conn() as c:
            row = c.execute("SELECT * FROM approval WHERE id=?", (aid,)).fetchone()
        return dict(row) if row else None

    def resolve_approval(self, aid, *, approved, actor):
        a = self.get_approval(aid)
        if not a or a["status"] != "pending":
            return a
        status = "approved" if approved else "denied"
        if _now() > a["expires_at"]:
            status = "expired"
        with self._conn() as c:
            c.execute("UPDATE approval SET status=?, resolved_at=? WHERE id=?",
                     (status, _now(), aid))
        return self.get_approval(aid)

    def find_valid_approval(self, *, owner, tool_id, account_id, input_hash, risk,
                           environment="local", target=""):
        """Return an approved, unexpired, unused approval bound to the EXACT
        action (same tool+account+input hash+risk+environment+target)."""
        with self._conn() as c:
            rows = c.execute("SELECT * FROM approval WHERE owner=? AND tool_id=? AND "
                            "account_id=? AND input_hash=? AND status='approved'",
                            (owner, tool_id, account_id, input_hash)).fetchall()
        now = _now()
        for r in rows:
            a = dict(r)
            if a["expires_at"] < now:
                continue
            if a["used"] >= a["max_uses"]:
                continue
            if int(a["risk"]) != int(risk):
                continue
            if a["environment"] != environment or a["target"] != target:
                continue
            return a
        return None

    def consume_approval(self, aid):
        with self._conn() as c:
            c.execute("UPDATE approval SET used=used+1 WHERE id=?", (aid,))

    def pending_approvals(self, owner):
        with self._conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT * FROM approval WHERE owner=? AND status='pending'", (owner,)).fetchall()]

    # ── webhook events (dedup + replay) ───────────────────────────────────
    def record_webhook(self, *, connector_id, dedup_key, event_ts, normalized):
        wid = _id("wh")
        try:
            with self._conn() as c:
                c.execute("INSERT INTO webhook_event(id,connector_id,dedup_key,received_at,"
                         "event_ts,normalized,status) VALUES(?,?,?,?,?,?,?)",
                         (wid, connector_id, dedup_key, _now(), event_ts,
                          json.dumps(normalized), "accepted"))
        except sqlite3.IntegrityError:
            return None  # replay/duplicate
        return wid

    def list_webhooks(self, connector_id=None, limit=50):
        q = "SELECT * FROM webhook_event"
        args = []
        if connector_id:
            q += " WHERE connector_id=?"; args.append(connector_id)
        q += " ORDER BY received_at DESC LIMIT ?"; args.append(limit)
        with self._conn() as c:
            return [dict(r) for r in c.execute(q, args).fetchall()]

    # ── sync jobs (checkpoints) ────────────────────────────────────────────
    def create_sync(self, *, owner, connector_id, batch_size=100):
        sid = _id("sync")
        now = _now()
        with self._conn() as c:
            c.execute("INSERT INTO sync_job(id,owner,connector_id,batch_size,state,"
                     "created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                     (sid, owner, connector_id, batch_size, "idle", now, now))
        return sid

    def get_sync(self, sid):
        with self._conn() as c:
            row = c.execute("SELECT * FROM sync_job WHERE id=?", (sid,)).fetchone()
        return dict(row) if row else None

    def checkpoint_sync(self, sid, *, cursor=None, page_token=None, processed=None, state=None):
        sets, args = ["updated_at=?", "last_sync=?"], [_now(), _now()]
        for k, v in (("cursor", cursor), ("page_token", page_token),
                     ("processed", processed), ("state", state)):
            if v is not None:
                sets.append(f"{k}=?"); args.append(v)
        args.append(sid)
        with self._conn() as c:
            c.execute(f"UPDATE sync_job SET {','.join(sets)} WHERE id=?", args)

    # ── rate buckets ──────────────────────────────────────────────────────
    def get_bucket(self, bucket):
        with self._conn() as c:
            row = c.execute("SELECT * FROM rate_bucket WHERE bucket=?", (bucket,)).fetchone()
        return dict(row) if row else None

    def set_bucket(self, bucket, *, remaining, limit_n, reset_at):
        with self._conn() as c:
            c.execute("INSERT OR REPLACE INTO rate_bucket VALUES(?,?,?,?,?)",
                     (bucket, remaining, limit_n, reset_at, _now()))

    def record_failure(self, *, connector_id, tool_id, fingerprint, failure_class):
        with self._conn() as c:
            c.execute("INSERT INTO failure VALUES(?,?,?,?,?,?)",
                     (_id("fail"), connector_id, tool_id, fingerprint, failure_class, _now()))

    def list_failures(self, limit=50):
        with self._conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT * FROM failure ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()]


_default: Optional[ConnectorStore] = None


def default_store() -> ConnectorStore:
    global _default
    if _default is None:
        _default = ConnectorStore()
    return _default
