"""M17.25 — Governed browser session lifecycle, ownership, and leases.

Distinct from cookie ``SessionManager`` (technical storage). This store records
authoritative ownership, scope, status transitions, leases, checkpoints, and
handoff state for interactive browser work.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_DB = ROOT / "data" / "browser_sessions" / "governed_sessions.db"

_lock = threading.RLock()


class SessionStatus(str, Enum):
    REQUESTED = "requested"
    POLICY_PENDING = "policy_pending"
    APPROVAL_PENDING = "approval_pending"
    READY = "ready"
    ACTIVE = "active"
    PAUSED_FOR_HUMAN = "paused_for_human"
    PAUSED_FOR_APPROVAL = "paused_for_approval"
    CHECKPOINTED = "checkpointed"
    RESUMING = "resuming"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    FAILED = "failed"
    RECONCILIATION_REQUIRED = "reconciliation_required"
    CLOSED = "closed"


# Deterministic allowed transitions
_TRANSITIONS: dict[SessionStatus, frozenset[SessionStatus]] = {
    SessionStatus.REQUESTED: frozenset({
        SessionStatus.POLICY_PENDING, SessionStatus.APPROVAL_PENDING,
        SessionStatus.READY, SessionStatus.CANCELLED, SessionStatus.FAILED,
    }),
    SessionStatus.POLICY_PENDING: frozenset({
        SessionStatus.APPROVAL_PENDING, SessionStatus.READY,
        SessionStatus.CANCELLED, SessionStatus.FAILED,
    }),
    SessionStatus.APPROVAL_PENDING: frozenset({
        SessionStatus.READY, SessionStatus.PAUSED_FOR_APPROVAL,
        SessionStatus.CANCELLED, SessionStatus.FAILED,
    }),
    SessionStatus.READY: frozenset({
        SessionStatus.ACTIVE, SessionStatus.CANCELLED, SessionStatus.EXPIRED,
    }),
    SessionStatus.ACTIVE: frozenset({
        SessionStatus.PAUSED_FOR_HUMAN, SessionStatus.PAUSED_FOR_APPROVAL,
        SessionStatus.CHECKPOINTED, SessionStatus.COMPLETED,
        SessionStatus.CANCELLED, SessionStatus.FAILED, SessionStatus.EXPIRED,
        SessionStatus.RECONCILIATION_REQUIRED, SessionStatus.CLOSED,
    }),
    SessionStatus.PAUSED_FOR_HUMAN: frozenset({
        SessionStatus.RESUMING, SessionStatus.CANCELLED, SessionStatus.EXPIRED,
        SessionStatus.FAILED, SessionStatus.CLOSED,
    }),
    SessionStatus.PAUSED_FOR_APPROVAL: frozenset({
        SessionStatus.ACTIVE, SessionStatus.READY, SessionStatus.CANCELLED,
        SessionStatus.EXPIRED, SessionStatus.FAILED,
    }),
    SessionStatus.CHECKPOINTED: frozenset({
        SessionStatus.ACTIVE, SessionStatus.RESUMING, SessionStatus.PAUSED_FOR_HUMAN,
        SessionStatus.COMPLETED, SessionStatus.CANCELLED, SessionStatus.EXPIRED,
        SessionStatus.CLOSED,
    }),
    SessionStatus.RESUMING: frozenset({
        SessionStatus.ACTIVE, SessionStatus.PAUSED_FOR_HUMAN,
        SessionStatus.FAILED, SessionStatus.CANCELLED, SessionStatus.EXPIRED,
    }),
    SessionStatus.COMPLETED: frozenset({SessionStatus.CLOSED}),
    SessionStatus.CANCELLED: frozenset({SessionStatus.CLOSED}),
    SessionStatus.EXPIRED: frozenset({SessionStatus.CLOSED, SessionStatus.RECONCILIATION_REQUIRED}),
    SessionStatus.FAILED: frozenset({
        SessionStatus.CLOSED, SessionStatus.RECONCILIATION_REQUIRED,
    }),
    SessionStatus.RECONCILIATION_REQUIRED: frozenset({
        SessionStatus.CLOSED, SessionStatus.FAILED, SessionStatus.COMPLETED,
    }),
    SessionStatus.CLOSED: frozenset(),
}

TERMINAL_SESSION = frozenset({
    SessionStatus.CLOSED, SessionStatus.CANCELLED, SessionStatus.EXPIRED,
    SessionStatus.COMPLETED, SessionStatus.FAILED,
})

ACTIONABLE_SESSION = frozenset({
    SessionStatus.READY, SessionStatus.ACTIVE, SessionStatus.CHECKPOINTED,
    SessionStatus.RESUMING,
})


class SessionError(RuntimeError):
    def __init__(self, code: str, message: str, *, details: Optional[dict] = None):
        self.code = code
        self.message = message
        self.details = dict(details or {})
        super().__init__(f"{code}: {message}")

    def as_dict(self) -> dict:
        return {"error": "browser_session", "code": self.code,
                "message": self.message, "details": self.details}


def assert_session_transition(cur: SessionStatus | str, nxt: SessionStatus | str) -> None:
    c = SessionStatus(cur) if not isinstance(cur, SessionStatus) else cur
    n = SessionStatus(nxt) if not isinstance(nxt, SessionStatus) else nxt
    if n not in _TRANSITIONS.get(c, frozenset()):
        raise SessionError(
            "INVALID_TRANSITION",
            f"cannot transition session {c.value} → {n.value}",
            details={"from": c.value, "to": n.value},
        )


@dataclass
class GovernedBrowserSession:
    session_id: str
    actor_id: str
    actor_type: str = "user"
    mission_id: str = ""
    mission_run_id: str = ""
    workflow_id: str = ""
    correlation_id: str = ""
    request_source: str = "api"
    browser_adapter: str = "fake"
    browser_profile_reference: str = ""
    target_scope: str = ""
    allowed_domains: list[str] = field(default_factory=list)
    allowed_action_classes: list[str] = field(default_factory=lambda: [
        "read_only", "low_interactive",
    ])
    risk_tier: str = "low"
    approval_scope: list[str] = field(default_factory=list)
    created_at: float = 0.0
    last_active_at: float = 0.0
    expires_at: float = 0.0
    status: str = SessionStatus.REQUESTED.value
    lease_owner: str = ""
    lease_expires_at: float = 0.0
    checkpoint_reference: str = ""
    human_handoff_state: str = ""
    sensitivity_classification: str = "general"
    artifact_retention_policy: str = "default"
    close_reason: str = ""
    reconciliation_status: str = ""
    current_url: str = ""
    current_origin: str = ""
    page_title: str = ""
    page_fingerprint: str = ""
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "GovernedBrowserSession":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore
        return cls(**{k: v for k, v in d.items() if k in known})

    @property
    def status_enum(self) -> SessionStatus:
        return SessionStatus(self.status)

    def is_expired(self, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        return bool(self.expires_at and now > self.expires_at)

    def lease_valid(self, worker: str, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        if not self.lease_owner:
            return True
        if self.lease_expires_at and now > self.lease_expires_at:
            return True  # stale lease free for re-claim
        return self.lease_owner == worker


_SCHEMA = """
CREATE TABLE IF NOT EXISTS browser_session (
  session_id TEXT PRIMARY KEY,
  actor_id TEXT NOT NULL,
  actor_type TEXT NOT NULL DEFAULT 'user',
  mission_id TEXT NOT NULL DEFAULT '',
  mission_run_id TEXT NOT NULL DEFAULT '',
  workflow_id TEXT NOT NULL DEFAULT '',
  correlation_id TEXT NOT NULL DEFAULT '',
  request_source TEXT NOT NULL DEFAULT 'api',
  browser_adapter TEXT NOT NULL DEFAULT 'fake',
  browser_profile_reference TEXT NOT NULL DEFAULT '',
  target_scope TEXT NOT NULL DEFAULT '',
  allowed_domains TEXT NOT NULL DEFAULT '[]',
  allowed_action_classes TEXT NOT NULL DEFAULT '[]',
  risk_tier TEXT NOT NULL DEFAULT 'low',
  approval_scope TEXT NOT NULL DEFAULT '[]',
  created_at REAL NOT NULL,
  last_active_at REAL NOT NULL,
  expires_at REAL NOT NULL DEFAULT 0,
  status TEXT NOT NULL,
  lease_owner TEXT NOT NULL DEFAULT '',
  lease_expires_at REAL NOT NULL DEFAULT 0,
  checkpoint_reference TEXT NOT NULL DEFAULT '',
  human_handoff_state TEXT NOT NULL DEFAULT '',
  sensitivity_classification TEXT NOT NULL DEFAULT 'general',
  artifact_retention_policy TEXT NOT NULL DEFAULT 'default',
  close_reason TEXT NOT NULL DEFAULT '',
  reconciliation_status TEXT NOT NULL DEFAULT '',
  current_url TEXT NOT NULL DEFAULT '',
  current_origin TEXT NOT NULL DEFAULT '',
  page_title TEXT NOT NULL DEFAULT '',
  page_fingerprint TEXT NOT NULL DEFAULT '',
  metadata TEXT NOT NULL DEFAULT '{}',
  transition_log TEXT NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS idx_bs_actor ON browser_session(actor_id);
CREATE INDEX IF NOT EXISTS idx_bs_mission ON browser_session(mission_id, mission_run_id);
CREATE INDEX IF NOT EXISTS idx_bs_status ON browser_session(status);

CREATE TABLE IF NOT EXISTS browser_action_ledger (
  action_id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  actor_id TEXT NOT NULL,
  mission_id TEXT NOT NULL DEFAULT '',
  mission_run_id TEXT NOT NULL DEFAULT '',
  action_type TEXT NOT NULL,
  action_class TEXT NOT NULL,
  idempotency_key TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL,
  target TEXT NOT NULL DEFAULT '',
  target_digest TEXT NOT NULL DEFAULT '',
  expected_effect TEXT NOT NULL DEFAULT '',
  approval_id TEXT NOT NULL DEFAULT '',
  result_summary TEXT NOT NULL DEFAULT '',
  failure_category TEXT NOT NULL DEFAULT '',
  execution_id TEXT NOT NULL DEFAULT '',
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL,
  payload_meta TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_bal_idem ON browser_action_ledger(idempotency_key);
CREATE INDEX IF NOT EXISTS idx_bal_session ON browser_action_ledger(session_id);

CREATE TABLE IF NOT EXISTS browser_handoff (
  handoff_id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  mission_id TEXT NOT NULL DEFAULT '',
  mission_run_id TEXT NOT NULL DEFAULT '',
  reason TEXT NOT NULL,
  required_human_action TEXT NOT NULL DEFAULT '',
  allowed_scope TEXT NOT NULL DEFAULT '[]',
  created_at REAL NOT NULL,
  expires_at REAL NOT NULL,
  status TEXT NOT NULL,
  requesting_actor TEXT NOT NULL DEFAULT '',
  assigned_human TEXT NOT NULL DEFAULT '',
  checkpoint_reference TEXT NOT NULL DEFAULT '',
  resume_token_reference TEXT NOT NULL DEFAULT '',
  evidence_reference TEXT NOT NULL DEFAULT '',
  resolution TEXT NOT NULL DEFAULT '',
  resolved_at REAL NOT NULL DEFAULT 0,
  metadata TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_bh_session ON browser_handoff(session_id);
CREATE INDEX IF NOT EXISTS idx_bh_status ON browser_handoff(status);

CREATE TABLE IF NOT EXISTS browser_checkpoint (
  checkpoint_id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  mission_id TEXT NOT NULL DEFAULT '',
  mission_run_id TEXT NOT NULL DEFAULT '',
  created_at REAL NOT NULL,
  page_url TEXT NOT NULL DEFAULT '',
  page_origin TEXT NOT NULL DEFAULT '',
  page_fingerprint TEXT NOT NULL DEFAULT '',
  page_title TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'valid',
  metadata TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_bcp_session ON browser_checkpoint(session_id);
"""


class BrowserSessionStore:
    """SQLite-backed governed browser session + action/handoff ledger."""

    def __init__(self, db_path: Path | str | None = None):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(_SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(str(self.db_path), timeout=30)
        c.row_factory = sqlite3.Row
        return c

    # ── sessions ──────────────────────────────────────────────────────────
    def create_session(
        self,
        *,
        actor_id: str,
        actor_type: str = "user",
        mission_id: str = "",
        mission_run_id: str = "",
        workflow_id: str = "",
        correlation_id: str = "",
        request_source: str = "api",
        browser_adapter: str = "fake",
        allowed_domains: list[str] | None = None,
        allowed_action_classes: list[str] | None = None,
        risk_tier: str = "low",
        approval_scope: list[str] | None = None,
        ttl_sec: float = 3600,
        target_scope: str = "",
        lease_owner: str = "",
        lease_ttl_sec: float = 120,
        metadata: dict | None = None,
    ) -> GovernedBrowserSession:
        if not (actor_id or "").strip() or actor_id in ("unknown", "anonymous"):
            raise SessionError("MISSING_ACTOR", "session requires actor_id")
        now = time.time()
        sid = f"bsess-{uuid.uuid4().hex[:16]}"
        sess = GovernedBrowserSession(
            session_id=sid,
            actor_id=actor_id,
            actor_type=actor_type,
            mission_id=mission_id,
            mission_run_id=mission_run_id,
            workflow_id=workflow_id,
            correlation_id=correlation_id or sid,
            request_source=request_source,
            browser_adapter=browser_adapter,
            target_scope=target_scope,
            allowed_domains=list(allowed_domains or []),
            allowed_action_classes=list(allowed_action_classes or [
                "read_only", "low_interactive",
            ]),
            risk_tier=risk_tier,
            approval_scope=list(approval_scope or []),
            created_at=now,
            last_active_at=now,
            expires_at=now + float(ttl_sec),
            status=SessionStatus.READY.value,
            lease_owner=lease_owner or actor_id,
            lease_expires_at=now + float(lease_ttl_sec) if lease_owner or actor_id else 0,
            metadata=dict(metadata or {}),
        )
        self._insert(sess)
        return sess

    def _insert(self, s: GovernedBrowserSession) -> None:
        with _lock, self._conn() as c:
            c.execute(
                "INSERT INTO browser_session VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    s.session_id, s.actor_id, s.actor_type, s.mission_id, s.mission_run_id,
                    s.workflow_id, s.correlation_id, s.request_source, s.browser_adapter,
                    s.browser_profile_reference, s.target_scope,
                    json.dumps(s.allowed_domains), json.dumps(s.allowed_action_classes),
                    s.risk_tier, json.dumps(s.approval_scope), s.created_at, s.last_active_at,
                    s.expires_at, s.status, s.lease_owner, s.lease_expires_at,
                    s.checkpoint_reference, s.human_handoff_state,
                    s.sensitivity_classification, s.artifact_retention_policy,
                    s.close_reason, s.reconciliation_status, s.current_url,
                    s.current_origin, s.page_title, s.page_fingerprint,
                    json.dumps(s.metadata), json.dumps([]),
                ),
            )
            c.commit()

    def _row_to_session(self, row: sqlite3.Row) -> GovernedBrowserSession:
        d = dict(row)
        d["allowed_domains"] = json.loads(d.pop("allowed_domains") or "[]")
        d["allowed_action_classes"] = json.loads(d.pop("allowed_action_classes") or "[]")
        d["approval_scope"] = json.loads(d.pop("approval_scope") or "[]")
        d["metadata"] = json.loads(d.pop("metadata") or "{}")
        d.pop("transition_log", None)
        return GovernedBrowserSession.from_dict(d)

    def get(self, session_id: str) -> Optional[GovernedBrowserSession]:
        with _lock, self._conn() as c:
            row = c.execute(
                "SELECT * FROM browser_session WHERE session_id=?", (session_id,)
            ).fetchone()
        return self._row_to_session(row) if row else None

    def require(self, session_id: str) -> GovernedBrowserSession:
        s = self.get(session_id)
        if s is None:
            raise SessionError("UNKNOWN_SESSION", f"unknown session {session_id}")
        return s

    def transition(
        self,
        session_id: str,
        new_status: SessionStatus | str,
        *,
        reason: str = "",
        extra: Optional[dict] = None,
    ) -> GovernedBrowserSession:
        with _lock, self._conn() as c:
            row = c.execute(
                "SELECT * FROM browser_session WHERE session_id=?", (session_id,)
            ).fetchone()
            if not row:
                raise SessionError("UNKNOWN_SESSION", f"unknown session {session_id}")
            s = self._row_to_session(row)
            nxt = SessionStatus(new_status) if not isinstance(new_status, SessionStatus) else new_status
            assert_session_transition(s.status, nxt)
            now = time.time()
            log = json.loads(row["transition_log"] or "[]")
            log.append({"from": s.status, "to": nxt.value, "at": now, "reason": reason})
            fields = {
                "status": nxt.value,
                "last_active_at": now,
                "transition_log": json.dumps(log[-50:]),
            }
            if reason and nxt in (SessionStatus.CANCELLED, SessionStatus.CLOSED, SessionStatus.FAILED):
                fields["close_reason"] = reason
            if extra:
                for k, v in extra.items():
                    if k in (
                        "checkpoint_reference", "human_handoff_state", "current_url",
                        "current_origin", "page_title", "page_fingerprint",
                        "reconciliation_status", "lease_owner", "lease_expires_at",
                        "approval_scope", "allowed_action_classes", "risk_tier",
                    ):
                        if k in ("approval_scope", "allowed_action_classes") and isinstance(v, list):
                            fields[k] = json.dumps(v)
                        else:
                            fields[k] = v
            sets = ", ".join(f"{k}=?" for k in fields)
            c.execute(
                f"UPDATE browser_session SET {sets} WHERE session_id=?",
                (*fields.values(), session_id),
            )
            c.commit()
        return self.require(session_id)

    def touch(self, session_id: str, **page_fields: Any) -> GovernedBrowserSession:
        with _lock, self._conn() as c:
            row = c.execute(
                "SELECT * FROM browser_session WHERE session_id=?", (session_id,)
            ).fetchone()
            if not row:
                raise SessionError("UNKNOWN_SESSION", f"unknown session {session_id}")
            now = time.time()
            fields = {"last_active_at": now}
            for k in ("current_url", "current_origin", "page_title", "page_fingerprint",
                      "checkpoint_reference", "human_handoff_state"):
                if k in page_fields and page_fields[k] is not None:
                    fields[k] = page_fields[k]
            if "status" in page_fields and page_fields["status"]:
                s = self._row_to_session(row)
                nxt = SessionStatus(page_fields["status"])
                assert_session_transition(s.status, nxt)
                fields["status"] = nxt.value
            sets = ", ".join(f"{k}=?" for k in fields)
            c.execute(
                f"UPDATE browser_session SET {sets} WHERE session_id=?",
                (*fields.values(), session_id),
            )
            c.commit()
        return self.require(session_id)

    def acquire_lease(
        self, session_id: str, worker: str, *, ttl_sec: float = 120
    ) -> GovernedBrowserSession:
        s = self.require(session_id)
        now = time.time()
        if s.is_expired(now):
            self.transition(session_id, SessionStatus.EXPIRED, reason="ttl_expired")
            raise SessionError("SESSION_EXPIRED", "session expired")
        if s.lease_owner and s.lease_owner != worker and s.lease_expires_at > now:
            raise SessionError(
                "LEASE_HELD",
                f"session leased by {s.lease_owner}",
                details={"lease_owner": s.lease_owner, "worker": worker},
            )
        with _lock, self._conn() as c:
            c.execute(
                "UPDATE browser_session SET lease_owner=?, lease_expires_at=?, last_active_at=? "
                "WHERE session_id=?",
                (worker, now + ttl_sec, now, session_id),
            )
            c.commit()
        return self.require(session_id)

    def release_lease(self, session_id: str, worker: str) -> GovernedBrowserSession:
        s = self.require(session_id)
        if s.lease_owner and s.lease_owner != worker:
            raise SessionError("LEASE_HELD", "cannot release another worker's lease")
        with _lock, self._conn() as c:
            c.execute(
                "UPDATE browser_session SET lease_owner='', lease_expires_at=0 WHERE session_id=?",
                (session_id,),
            )
            c.commit()
        return self.require(session_id)

    def assert_access(
        self,
        session_id: str,
        *,
        actor_id: str,
        mission_id: str = "",
        mission_run_id: str = "",
        worker: str = "",
        allow_recovery: bool = False,
    ) -> GovernedBrowserSession:
        s = self.require(session_id)
        now = time.time()
        if s.is_expired(now):
            try:
                self.transition(session_id, SessionStatus.EXPIRED, reason="ttl_expired")
            except SessionError:
                pass
            raise SessionError("SESSION_EXPIRED", "session expired")
        if s.status_enum in (SessionStatus.CLOSED, SessionStatus.CANCELLED):
            raise SessionError("SESSION_TERMINAL", f"session is {s.status}")
        if s.actor_id != actor_id and not allow_recovery:
            raise SessionError(
                "OWNERSHIP_DENIED",
                "actor does not own this browser session",
                details={"owner": s.actor_id, "actor": actor_id},
            )
        if mission_id and s.mission_id and s.mission_id != mission_id:
            raise SessionError(
                "MISSION_MISMATCH",
                "mission does not match session ownership",
                details={"session_mission": s.mission_id, "mission_id": mission_id},
            )
        if mission_run_id and s.mission_run_id and s.mission_run_id != mission_run_id:
            raise SessionError(
                "RUN_MISMATCH",
                "mission_run_id does not match session",
                details={"session_run": s.mission_run_id, "mission_run_id": mission_run_id},
            )
        if worker and not s.lease_valid(worker, now):
            raise SessionError(
                "LEASE_HELD",
                "another worker holds the session lease",
                details={"lease_owner": s.lease_owner, "worker": worker},
            )
        return s

    # ── action ledger ─────────────────────────────────────────────────────
    def record_action(
        self,
        *,
        action_id: str,
        session_id: str,
        actor_id: str,
        action_type: str,
        action_class: str,
        status: str,
        mission_id: str = "",
        mission_run_id: str = "",
        idempotency_key: str = "",
        target: str = "",
        target_digest: str = "",
        expected_effect: str = "",
        approval_id: str = "",
        result_summary: str = "",
        failure_category: str = "",
        execution_id: str = "",
        payload_meta: Optional[dict] = None,
    ) -> dict:
        now = time.time()
        with _lock, self._conn() as c:
            if idempotency_key:
                prev = c.execute(
                    "SELECT * FROM browser_action_ledger WHERE idempotency_key=?",
                    (idempotency_key,),
                ).fetchone()
                if prev:
                    return dict(prev)
            c.execute(
                "INSERT OR REPLACE INTO browser_action_ledger VALUES "
                "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    action_id, session_id, actor_id, mission_id, mission_run_id,
                    action_type, action_class, idempotency_key, status, target,
                    target_digest, expected_effect, approval_id, result_summary,
                    failure_category, execution_id, now, now,
                    json.dumps(payload_meta or {}),
                ),
            )
            c.commit()
        return self.get_action(action_id) or {}

    def update_action(self, action_id: str, **fields: Any) -> dict:
        allowed = {
            "status", "result_summary", "failure_category", "execution_id",
            "target", "target_digest", "approval_id",
        }
        with _lock, self._conn() as c:
            row = c.execute(
                "SELECT * FROM browser_action_ledger WHERE action_id=?", (action_id,)
            ).fetchone()
            if not row:
                raise SessionError("UNKNOWN_ACTION", f"unknown action {action_id}")
            sets = {"updated_at": time.time()}
            for k, v in fields.items():
                if k in allowed:
                    sets[k] = v
            sql = ", ".join(f"{k}=?" for k in sets)
            c.execute(
                f"UPDATE browser_action_ledger SET {sql} WHERE action_id=?",
                (*sets.values(), action_id),
            )
            c.commit()
        return self.get_action(action_id) or {}

    def get_action(self, action_id: str) -> Optional[dict]:
        with _lock, self._conn() as c:
            row = c.execute(
                "SELECT * FROM browser_action_ledger WHERE action_id=?", (action_id,)
            ).fetchone()
        return dict(row) if row else None

    def find_action_by_idempotency(self, key: str) -> Optional[dict]:
        if not key:
            return None
        with _lock, self._conn() as c:
            row = c.execute(
                "SELECT * FROM browser_action_ledger WHERE idempotency_key=?", (key,)
            ).fetchone()
        return dict(row) if row else None

    # ── handoffs ──────────────────────────────────────────────────────────
    def create_handoff(
        self,
        *,
        session_id: str,
        reason: str,
        required_human_action: str = "",
        allowed_scope: list[str] | None = None,
        requesting_actor: str = "",
        mission_id: str = "",
        mission_run_id: str = "",
        checkpoint_reference: str = "",
        ttl_sec: float = 1800,
        metadata: dict | None = None,
    ) -> dict:
        hid = f"ho-{uuid.uuid4().hex[:14]}"
        now = time.time()
        token = f"rt-{uuid.uuid4().hex}"
        with _lock, self._conn() as c:
            c.execute(
                "INSERT INTO browser_handoff VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    hid, session_id, mission_id, mission_run_id, reason,
                    required_human_action, json.dumps(allowed_scope or []),
                    now, now + ttl_sec, "awaiting_human", requesting_actor, "",
                    checkpoint_reference, token, "", "", 0,
                    json.dumps(metadata or {}),
                ),
            )
            c.commit()
        return self.get_handoff(hid) or {}

    def get_handoff(self, handoff_id: str) -> Optional[dict]:
        with _lock, self._conn() as c:
            row = c.execute(
                "SELECT * FROM browser_handoff WHERE handoff_id=?", (handoff_id,)
            ).fetchone()
        if not row:
            return None
        d = dict(row)
        d["allowed_scope"] = json.loads(d.get("allowed_scope") or "[]")
        d["metadata"] = json.loads(d.get("metadata") or "{}")
        return d

    def update_handoff(self, handoff_id: str, **fields: Any) -> dict:
        allowed = {
            "status", "assigned_human", "resolution", "resolved_at",
            "evidence_reference", "checkpoint_reference",
        }
        with _lock, self._conn() as c:
            row = c.execute(
                "SELECT * FROM browser_handoff WHERE handoff_id=?", (handoff_id,)
            ).fetchone()
            if not row:
                raise SessionError("UNKNOWN_HANDOFF", f"unknown handoff {handoff_id}")
            sets = {k: v for k, v in fields.items() if k in allowed}
            if not sets:
                return self.get_handoff(handoff_id) or {}
            sql = ", ".join(f"{k}=?" for k in sets)
            c.execute(
                f"UPDATE browser_handoff SET {sql} WHERE handoff_id=?",
                (*sets.values(), handoff_id),
            )
            c.commit()
        return self.get_handoff(handoff_id) or {}

    def active_handoff_for_session(self, session_id: str) -> Optional[dict]:
        with _lock, self._conn() as c:
            row = c.execute(
                "SELECT * FROM browser_handoff WHERE session_id=? AND status IN "
                "('requested','awaiting_human','claimed','in_progress','resume_pending') "
                "ORDER BY created_at DESC LIMIT 1",
                (session_id,),
            ).fetchone()
        if not row:
            return None
        d = dict(row)
        d["allowed_scope"] = json.loads(d.get("allowed_scope") or "[]")
        d["metadata"] = json.loads(d.get("metadata") or "{}")
        return d

    # ── checkpoints ───────────────────────────────────────────────────────
    def create_checkpoint(
        self,
        session_id: str,
        *,
        mission_id: str = "",
        mission_run_id: str = "",
        page_url: str = "",
        page_origin: str = "",
        page_fingerprint: str = "",
        page_title: str = "",
        metadata: dict | None = None,
    ) -> dict:
        cid = f"bcp-{uuid.uuid4().hex[:14]}"
        now = time.time()
        with _lock, self._conn() as c:
            c.execute(
                "INSERT INTO browser_checkpoint VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    cid, session_id, mission_id, mission_run_id, now,
                    page_url, page_origin, page_fingerprint, page_title,
                    "valid", json.dumps(metadata or {}),
                ),
            )
            c.commit()
        return self.get_checkpoint(cid) or {}

    def get_checkpoint(self, checkpoint_id: str) -> Optional[dict]:
        with _lock, self._conn() as c:
            row = c.execute(
                "SELECT * FROM browser_checkpoint WHERE checkpoint_id=?",
                (checkpoint_id,),
            ).fetchone()
        if not row:
            return None
        d = dict(row)
        d["metadata"] = json.loads(d.get("metadata") or "{}")
        return d

    def invalidate_checkpoint(self, checkpoint_id: str, reason: str = "") -> None:
        with _lock, self._conn() as c:
            c.execute(
                "UPDATE browser_checkpoint SET status=? WHERE checkpoint_id=?",
                (f"invalid:{reason}"[:40], checkpoint_id),
            )
            c.commit()


_STORE: Optional[BrowserSessionStore] = None
_STORE_LOCK = threading.Lock()


def default_session_store(**kwargs) -> BrowserSessionStore:
    global _STORE
    with _STORE_LOCK:
        if kwargs:
            return BrowserSessionStore(**kwargs)
        if _STORE is None:
            _STORE = BrowserSessionStore()
        return _STORE


def reset_session_store() -> None:
    global _STORE
    with _STORE_LOCK:
        _STORE = None
