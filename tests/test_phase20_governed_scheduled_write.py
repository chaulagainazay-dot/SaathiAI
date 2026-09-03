"""Phase 20 — a legitimate scheduled write, and exactly one of it.

Phase 19 proved no external write escapes authority. The complementary property
is that a legitimate one can pass *through* it without becoming replayable, and
that is what these tests are for. The hard half is not the success: it is that
a scheduler restart, a duplicate trigger, a retry and thirty-two concurrent
workers all produce **one** external attempt.

Telegram is the writer under test because it is the only provider in the
repository with a real connector adapter, a registered `ToolDef`
(`risk_class=EXTERNAL_SIDE_EFFECT`, `mutation=IRREVERSIBLE`, `idempotent=False`)
and a connector authority model. Being non-idempotent and irreversible makes it
the honest case rather than the easy one: nothing here can lean on a provider
retry being harmless.

No real provider is contacted. The HTTP clients are replaced with ones that
raise, so a real request is a failure rather than an unnoticed message.
"""
from __future__ import annotations

import ast
import concurrent.futures
import pathlib
import threading
from datetime import datetime, timedelta, timezone

import pytest

from saathi.agent_runtime.contracts import AuthorityClass
from saathi.execution.authorization_sources import current_actor
from saathi.execution.egress import EgressDenied, EgressGrant, governed_egress
from saathi.execution.scheduled_write import (
    AMBIGUOUS,
    CLAIMED_BY_OTHER,
    EXECUTED,
    NO_ORIGINATING_USER,
    OCCURRENCE_TTL_SEC,
    REFUSED,
    SCOPE_SCHEDULED,
    delegation_id_for,
    execute_scheduled_write,
    idempotency_key_for,
    occurrence_id,
    schedule_occurrence,
)
from saathi.security.store import SecurityStore

JOB = "telegram_daily_digest"
ACTION = "telegram.send_message"
AT = datetime(2026, 9, 3, 9, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """A real request is a certification failure, not a silent side effect."""
    import httpx
    import requests

    def _boom(*a, **k):
        raise AssertionError("a test attempted to contact a real provider")

    for mod in (httpx, requests):
        for verb in ("post", "put", "patch", "delete", "get", "request"):
            monkeypatch.setattr(mod, verb, _boom, raising=False)


@pytest.fixture()
def store(tmp_path):
    from tests.support.auth_state import make_active

    s = SecurityStore(db_path=tmp_path / "security.db")
    make_active(s)
    return s


def _user(store, name="owner", *, role="role-owner") -> str:
    import time as _t

    uid = store.owner_id() if name == "owner" else f"u_{name}"
    if name != "owner":
        now = _t.time()
        store.db.execute(
            "INSERT OR IGNORE INTO users (id, email, name, status, created_at,"
            " updated_at) VALUES (?,?,?,'active',?,?)",
            (uid, f"{name}@example.test", name, now, now))
    store.db.execute("DELETE FROM user_roles WHERE user_id=?", (uid,))
    if role:
        store.db.execute("INSERT INTO user_roles (user_id, role_id, assigned_at)"
                         " VALUES (?,?,?)", (uid, role, 0))
    store.db.commit()
    return uid


class _Sink:
    """Counts external attempts. This count is the whole milestone.

    Asserts the Phase 19 grant is held at the moment of the write: a sink that
    only counted would prove the plumbing runs, not that it is governed.
    """

    def __init__(self):
        self.sends: list[dict] = []
        self.grants: list = []
        self._lock = threading.Lock()

    def send(self, idempotency_key: str) -> dict:
        from saathi.execution.egress import guard

        grant = guard("telegram.send_message", operation="scheduled_digest")
        with self._lock:
            self.grants.append(grant)
            self.sends.append({"idempotency_key": idempotency_key,
                               "actor": current_actor()})
        return {"ok": True, "message_id": len(self.sends),
                # A provider echo carrying a credential, which is how real
                # provider responses leak.
                "echo": {"authorization": "Bearer synthetic-abc123def456"}}


@pytest.fixture()
def sink():
    return _Sink()


def _governed_send(sink):
    """A `send` that runs inside a grant, standing in for the connector
    handler's dispatch. The grant is opened by execution infrastructure, never
    by the scheduled job itself."""
    def _send(idempotency_key: str):
        grant = EgressGrant(intent_id=f"i-{idempotency_key[:8]}",
                            intent_digest=idempotency_key, actor="scheduler",
                            operation=ACTION)
        with governed_egress(grant):
            return sink.send(idempotency_key)
    return _send


# ── identity is deterministic and occurrence-scoped ────────────────────────

def test_the_same_occurrence_derives_the_same_identity():
    """A restart must land on the same names, or nothing downstream dedupes."""
    a = occurrence_id(JOB, at=AT)
    b = occurrence_id(JOB, at=AT.replace(hour=23, minute=59))
    assert a == b == f"{JOB}@2026-09-03"
    assert delegation_id_for("u1", a) == delegation_id_for("u1", b)
    assert idempotency_key_for(a, ACTION) == idempotency_key_for(b, ACTION)


def test_a_different_occurrence_is_different_work():
    """Tomorrow's digest is not a replay of today's."""
    today = occurrence_id(JOB, at=AT)
    tomorrow = occurrence_id(JOB, at=AT + timedelta(days=1))
    assert today != tomorrow
    assert delegation_id_for("u1", today) != delegation_id_for("u1", tomorrow)
    assert idempotency_key_for(today, ACTION) != idempotency_key_for(tomorrow, ACTION)


@pytest.mark.parametrize("field", ["user", "job", "action"])
def test_identity_does_not_collapse_genuinely_different_work(field):
    occ = occurrence_id(JOB, at=AT)
    other_occ = occurrence_id("other_job", at=AT)
    if field == "user":
        assert delegation_id_for("u1", occ) != delegation_id_for("u2", occ)
    elif field == "job":
        assert delegation_id_for("u1", occ) != delegation_id_for("u1", other_occ)
    else:
        assert idempotency_key_for(occ, ACTION) != idempotency_key_for(occ, "other")


def test_the_idempotency_key_satisfies_the_intent_contract():
    """64 hex characters -- what `ToolIntent.validate` requires."""
    key = idempotency_key_for(occurrence_id(JOB, at=AT), ACTION)
    assert len(key) == 64 and int(key, 16) >= 0


# ── the positive control ───────────────────────────────────────────────────

def test_a_scheduled_write_executes_once_under_the_real_user(store, sink):
    """The whole point: it works, as the person who authorized it, holding a
    Phase 19 grant, with no request context anywhere."""
    uid = _user(store)
    assert current_actor() is None, "no ambient identity to lean on"

    schedule_occurrence(user_id=uid, job=JOB, action=ACTION, at=AT, store=store)
    result = execute_scheduled_write(job=JOB, action=ACTION, at=AT,
                                     send=_governed_send(sink), store=store)

    assert result.executed, result.reason_code
    assert result.actor == uid
    assert len(sink.sends) == 1
    assert sink.sends[0]["actor"] == uid, "the send ran as the originating user"
    assert sink.grants[0].intent_digest == idempotency_key_for(
        occurrence_id(JOB, at=AT), ACTION)
    assert current_actor() is None, "identity must not outlive the write"


def test_the_scheduled_write_needs_no_request_context(store, sink):
    """It runs in a thread that never saw an HTTP request, as a real worker
    would."""
    uid = _user(store)
    schedule_occurrence(user_id=uid, job=JOB, action=ACTION, at=AT, store=store)
    out: dict = {}

    def worker():
        out["r"] = execute_scheduled_write(job=JOB, action=ACTION, at=AT,
                                           send=_governed_send(sink), store=store)

    t = threading.Thread(target=worker)
    t.start(); t.join()
    assert out["r"].executed and len(sink.sends) == 1


# ── replay: the hard half ──────────────────────────────────────────────────

def test_a_second_trigger_of_the_same_occurrence_sends_nothing(store, sink):
    uid = _user(store)
    schedule_occurrence(user_id=uid, job=JOB, action=ACTION, at=AT, store=store)
    first = execute_scheduled_write(job=JOB, action=ACTION, at=AT,
                                    send=_governed_send(sink), store=store)
    second = execute_scheduled_write(job=JOB, action=ACTION, at=AT,
                                     send=_governed_send(sink), store=store)
    assert first.executed and not second.executed
    assert second.reason_code in (CLAIMED_BY_OTHER, "delegation.exhausted")
    assert len(sink.sends) == 1, "the occurrence sent twice"


def test_a_scheduler_restart_inside_the_catchup_window_sends_nothing(store, sink):
    """The Phase 19 finding, closed. `fired` is memory-only, so a restart makes
    the job eligible again; the durable claim is what stops the second send."""
    uid = _user(store)
    schedule_occurrence(user_id=uid, job=JOB, action=ACTION, at=AT, store=store)
    execute_scheduled_write(job=JOB, action=ACTION, at=AT,
                            send=_governed_send(sink), store=store)

    # Restart: every in-memory scheduler fact is gone. Re-scheduling the same
    # occurrence must find the existing grant, not mint a second one.
    again = schedule_occurrence(user_id=uid, job=JOB, action=ACTION, at=AT,
                                store=store)
    assert again == delegation_id_for(uid, occurrence_id(JOB, at=AT))
    replay = execute_scheduled_write(job=JOB, action=ACTION, at=AT,
                                     send=_governed_send(sink), store=store)
    assert not replay.executed
    assert len(sink.sends) == 1


def test_rescheduling_never_mints_a_second_grant(store):
    uid = _user(store)
    ids = {schedule_occurrence(user_id=uid, job=JOB, action=ACTION, at=AT,
                               store=store) for _ in range(10)}
    assert len(ids) == 1
    rows = store.db.execute(
        "SELECT COUNT(*) FROM authority_delegation WHERE scope_kind=? AND scope_ref=?",
        (SCOPE_SCHEDULED, occurrence_id(JOB, at=AT))).fetchone()
    assert rows[0] == 1


def test_the_next_occurrence_is_allowed_to_send(store, sink):
    """Replay protection must not become a permanent block: tomorrow is
    different work and must go through."""
    uid = _user(store)
    tomorrow = AT + timedelta(days=1)
    for when in (AT, tomorrow):
        schedule_occurrence(user_id=uid, job=JOB, action=ACTION, at=when, store=store)
        assert execute_scheduled_write(job=JOB, action=ACTION, at=when,
                                       send=_governed_send(sink),
                                       store=store).executed
    assert len(sink.sends) == 2


# ── concurrency: one winner ────────────────────────────────────────────────

@pytest.mark.parametrize("workers", [2, 16, 32])
def test_racing_workers_produce_exactly_one_external_attempt(store, sink, workers):
    """Counted at the side effect, not inferred from database state."""
    uid = _user(store)
    schedule_occurrence(user_id=uid, job=JOB, action=ACTION, at=AT, store=store)
    barrier = threading.Barrier(workers)

    def attempt():
        barrier.wait()
        return execute_scheduled_write(job=JOB, action=ACTION, at=AT,
                                       send=_governed_send(sink), store=store)

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        results = [f.result() for f in [pool.submit(attempt) for _ in range(workers)]]

    assert len(sink.sends) == 1, f"{len(sink.sends)} external attempts with {workers} workers"
    assert sum(1 for r in results if r.executed) == 1


# ── authority: every gate refuses ──────────────────────────────────────────

def test_an_unscheduled_occurrence_has_no_originating_user(store, sink):
    result = execute_scheduled_write(job=JOB, action=ACTION, at=AT,
                                     send=_governed_send(sink), store=store)
    assert result.reason_code == NO_ORIGINATING_USER
    assert sink.sends == []


def test_a_revoked_role_stops_the_scheduled_write(store, sink):
    """Scheduling is not permanent permission: the check is at execution."""
    uid = _user(store)
    schedule_occurrence(user_id=uid, job=JOB, action=ACTION, at=AT, store=store)
    store.db.execute("DELETE FROM user_roles WHERE user_id=?", (uid,))
    store.db.commit()

    result = execute_scheduled_write(job=JOB, action=ACTION, at=AT,
                                     send=_governed_send(sink), store=store)
    assert result.reason_code == "delegation.rbac_revoked"
    assert sink.sends == []


def test_a_viewer_cannot_hold_a_scheduled_write(store, sink):
    uid = _user(store, "viewer", role="role-viewer")
    schedule_occurrence(user_id=uid, job=JOB, action=ACTION, at=AT, store=store)
    result = execute_scheduled_write(job=JOB, action=ACTION, at=AT,
                                     send=_governed_send(sink), store=store)
    assert result.reason_code == "delegation.rbac_revoked"
    assert sink.sends == []


def test_a_disabled_user_stops_the_scheduled_write(store, sink):
    uid = _user(store)
    schedule_occurrence(user_id=uid, job=JOB, action=ACTION, at=AT, store=store)
    store.db.execute("UPDATE users SET status='disabled' WHERE id=?", (uid,))
    store.db.commit()
    result = execute_scheduled_write(job=JOB, action=ACTION, at=AT,
                                     send=_governed_send(sink), store=store)
    assert result.reason_code == "delegation.user_unavailable"
    assert sink.sends == []


def test_a_revoked_delegation_stops_the_scheduled_write(store, sink):
    uid = _user(store)
    did = schedule_occurrence(user_id=uid, job=JOB, action=ACTION, at=AT, store=store)
    store.revoke_delegation(did)
    result = execute_scheduled_write(job=JOB, action=ACTION, at=AT,
                                     send=_governed_send(sink), store=store)
    assert result.reason_code == "delegation.revoked"
    assert sink.sends == []


def test_an_expired_occurrence_stops_the_scheduled_write(store, sink):
    uid = _user(store)
    did = schedule_occurrence(user_id=uid, job=JOB, action=ACTION, at=AT, store=store)
    store.db.execute("UPDATE authority_delegation SET expires_at=1 WHERE delegation_id=?",
                     (did,))
    store.db.commit()
    result = execute_scheduled_write(job=JOB, action=ACTION, at=AT,
                                     send=_governed_send(sink), store=store)
    assert result.reason_code == "delegation.expired"
    assert sink.sends == []


def test_another_users_delegation_does_not_transfer(store, sink):
    """The occurrence resolves to whoever actually scheduled it."""
    alice = _user(store, "alice")
    _user(store, "bob")
    schedule_occurrence(user_id=alice, job=JOB, action=ACTION, at=AT, store=store)
    result = execute_scheduled_write(job=JOB, action=ACTION, at=AT,
                                     send=_governed_send(sink), store=store)
    assert result.actor == alice and result.actor != "u_bob"


def test_a_delegation_for_another_job_does_not_authorize_this_one(store, sink):
    uid = _user(store)
    schedule_occurrence(user_id=uid, job="other_job", action=ACTION, at=AT, store=store)
    result = execute_scheduled_write(job=JOB, action=ACTION, at=AT,
                                     send=_governed_send(sink), store=store)
    assert result.reason_code == NO_ORIGINATING_USER
    assert sink.sends == []


def test_no_session_token_is_persisted_with_the_occurrence(store):
    uid = _user(store)
    did = schedule_occurrence(user_id=uid, job=JOB, action=ACTION, at=AT, store=store)
    record = store.get_delegation(did)
    blob = str(record).lower()
    for forbidden in ("token", "cookie", "password", "bearer", "session"):
        assert forbidden not in blob, forbidden


# ── the Phase 19 guard still owns the side effect ──────────────────────────

def test_the_send_is_refused_without_a_grant(store, sink):
    """Winning the claim is not permission to write. The guard is separate."""
    uid = _user(store)
    schedule_occurrence(user_id=uid, job=JOB, action=ACTION, at=AT, store=store)

    def ungoverned(idempotency_key):
        return sink.send(idempotency_key)   # no grant opened

    result = execute_scheduled_write(job=JOB, action=ACTION, at=AT,
                                     send=ungoverned, store=store)
    assert result.outcome == AMBIGUOUS
    assert sink.sends == [], "the guard must stop the write"


def test_the_scheduled_writer_cannot_open_a_grant():
    """Static: only execution infrastructure may open the Phase 19 grant, and
    the scheduled-write module is not that."""
    source = pathlib.Path("saathi/execution/scheduled_write.py").read_text()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id != "governed_egress", "scheduled writer opens a grant"


def test_the_scheduled_writer_calls_no_raw_external_client():
    tree = ast.parse(pathlib.Path("saathi/execution/scheduled_write.py").read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in ("post", "put", "patch",
                                                             "delete"):
            recv = node.value
            name = recv.id if isinstance(recv, ast.Name) else ""
            assert name not in ("httpx", "requests", "aiohttp"), "raw client call"


def test_the_scheduled_writer_does_not_fabricate_an_actor():
    """The actor comes from the durable record. A literal identity here would
    be the Phase 17 defect returning."""
    tree = ast.parse(pathlib.Path("saathi/execution/scheduled_write.py").read_text())
    docstrings = {id(n.value) for n in ast.walk(tree)
                  if isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)}
    literals = [n.value for n in ast.walk(tree)
                if isinstance(n, ast.Constant) and isinstance(n.value, str)
                and id(n) not in docstrings]
    assert not any("ajay" in v.lower() or v.startswith("user:") for v in literals)


# ── ambiguity is reported, never resolved by guessing ──────────────────────

def test_a_failure_after_the_claim_is_ambiguous_not_failed(store, sink):
    """`telegram.send_message` is registered non-idempotent and irreversible, so
    a crash after the request left cannot be retried and cannot be called a
    success. It is reported as what it is."""
    uid = _user(store)
    schedule_occurrence(user_id=uid, job=JOB, action=ACTION, at=AT, store=store)

    def exploding(idempotency_key):
        raise RuntimeError("connection reset after send")

    result = execute_scheduled_write(job=JOB, action=ACTION, at=AT,
                                     send=exploding, store=store)
    assert result.outcome == AMBIGUOUS
    assert not result.executed


def test_an_ambiguous_outcome_does_not_free_the_claim(store, sink):
    """The dangerous recovery is a retry that duplicates a delivered message."""
    uid = _user(store)
    schedule_occurrence(user_id=uid, job=JOB, action=ACTION, at=AT, store=store)

    def exploding(idempotency_key):
        raise RuntimeError("connection reset")

    execute_scheduled_write(job=JOB, action=ACTION, at=AT, send=exploding, store=store)
    retry = execute_scheduled_write(job=JOB, action=ACTION, at=AT,
                                    send=_governed_send(sink), store=store)
    assert not retry.executed
    assert sink.sends == [], "an ambiguous send must not be retried automatically"


def test_the_ambiguous_detail_carries_no_credential(store):
    uid = _user(store)
    schedule_occurrence(user_id=uid, job=JOB, action=ACTION, at=AT, store=store)
    fake = "sk-abcdefghijklmnop1234567890"

    def exploding(idempotency_key):
        raise RuntimeError(f"401 using {fake}")

    result = execute_scheduled_write(job=JOB, action=ACTION, at=AT,
                                     send=exploding, store=store)
    assert result.outcome == AMBIGUOUS
    assert fake not in result.detail
    assert "401" in result.detail, "diagnostic value survives"


# ── result sanitization ────────────────────────────────────────────────────

def test_the_provider_result_is_sanitised_before_it_leaves(store, sink):
    from saathi.execution.sanitization import sanitize

    uid = _user(store)
    schedule_occurrence(user_id=uid, job=JOB, action=ACTION, at=AT, store=store)
    result = execute_scheduled_write(job=JOB, action=ACTION, at=AT,
                                     send=_governed_send(sink), store=store)
    cleaned, report = sanitize(result.result)
    assert "synthetic-abc123def456" not in str(cleaned)
    assert cleaned["message_id"] == 1, "identifiers survive"
    assert report.redaction_count >= 1


# ── audit ──────────────────────────────────────────────────────────────────

def test_the_attempt_is_auditable_end_to_end(store, sink):
    uid = _user(store)
    did = schedule_occurrence(user_id=uid, job=JOB, action=ACTION, at=AT, store=store)
    execute_scheduled_write(job=JOB, action=ACTION, at=AT,
                            send=_governed_send(sink), store=store)

    events = store.audit_recent(limit=20)
    used = [e for e in events if e["event"] == "delegation.used"]
    assert used, "the successful attempt left no audit"
    blob = str(events)
    assert did[:16] in blob and uid in blob
    for forbidden in ("password", "bearer ", "x-baadar-session", "synthetic-abc"):
        assert forbidden not in blob.lower()


def test_a_refused_attempt_is_audited_with_a_reason(store, sink):
    uid = _user(store)
    did = schedule_occurrence(user_id=uid, job=JOB, action=ACTION, at=AT, store=store)
    store.revoke_delegation(did)
    execute_scheduled_write(job=JOB, action=ACTION, at=AT,
                            send=_governed_send(sink), store=store)
    denied = [e for e in store.audit_recent(limit=20)
              if e["event"] == "delegation.denied"]
    assert denied and "revoked" in str(denied)


# ── the registry metadata this design rests on ─────────────────────────────

def test_telegram_is_registered_with_the_authority_this_design_assumes():
    """If this metadata changes, the guarantees stated here stop being true."""
    from saathi.connectors.platform import registry as R
    from saathi.connectors.platform.models import APPROVAL_THRESHOLD, MutationClass

    R._bootstrap()
    tool = R.get_tool("telegram.send_message")
    assert tool is not None
    assert int(tool.risk_class) >= int(APPROVAL_THRESHOLD), "must require approval"
    assert tool.idempotent is False, "the design must not assume provider retry safety"
    assert tool.mutation_class is MutationClass.IRREVERSIBLE

    connector = R.get_connector("telegram")
    assert connector.local is False and connector.auth_type == "token"


def test_the_occurrence_lifetime_is_bounded():
    assert 0 < OCCURRENCE_TTL_SEC <= 24 * 3600


# ══════════════════════════════════════════════════════════════════════════
# The full vertical slice: through the real ExecutionGateway boundary.
#
# Everything above proves the scheduled-write layer. This proves the layer
# below it — a real ToolIntent admitted by the real UniversalBoundary, whose
# handler dispatch opens the Phase 19 grant, reaching a local sink. It also
# exercises the boundary's *own* replay protection, which keys on the same
# identity the delegation does.
# ══════════════════════════════════════════════════════════════════════════

def _tool_intent(idempotency_key: str, actor: str):
    import uuid

    from saathi.execution.toolintent import (
        ApprovalLevel, BusinessUnit, RiskLevel, ToolIntent)

    return ToolIntent(
        intent_id=str(uuid.uuid4()), correlation_id=str(uuid.uuid4()),
        actor_id=f"user:{actor}", mission_id=JOB, capability="send_message",
        connector_id="local", operation="telegram.send_message",
        reason="phase20 scheduled digest",
        risk_level=RiskLevel.HIGH, approval_level=ApprovalLevel.L4,
        idempotency_key=idempotency_key,
        parameters={"chat_id": "@test", "text": "digest"},
        metadata={"family": "local", "occurrence": occurrence_id(JOB, at=AT)},
        business_unit=BusinessUnit.MR_YETI)


@pytest.fixture()
def boundary(tmp_path):
    from saathi.execution.store import ExecutionStore
    from saathi.execution.universal import UniversalBoundary

    return UniversalBoundary(store=ExecutionStore(tmp_path / "exec.db"))


def _approve(boundary, intent, actor: str) -> str:
    """Bind a real, single-use approval to this exact intent's digest.

    The real approval store and the real binding -- an operator does this
    through the approval route in production. What would be illegitimate is
    skipping the gate; creating the approval a human would create is fixture
    setup, and the binding is to the digest, so it authorizes this action and
    no other.
    """
    import time as _t

    from saathi.execution.record import tool_intent_digest

    approval_id = f"appr-{tool_intent_digest(intent)[:12]}"
    boundary.store.bind_approval(approval_id, digest=tool_intent_digest(intent),
                                 actor=f"user:{actor}", expires_at=_t.time() + 3600,
                                 max_uses=1)
    return approval_id


def test_the_boundary_withholds_a_risk_three_send_without_approval(store, sink,
                                                                   boundary):
    """The negative control for the slice below, and worth more than the
    positive: `telegram.send_message` is EXTERNAL_SIDE_EFFECT and irreversible,
    so an unapproved scheduled send must stop at the gate rather than reach a
    provider."""
    uid = _user(store)
    key = idempotency_key_for(occurrence_id(JOB, at=AT), ACTION)

    def handler(intent, rec):
        sink.send(intent.idempotency_key)
        return {"status": "succeeded"}

    boundary.register_handler("local", handler)
    rec = boundary.submit(_tool_intent(key, uid), handler=handler)

    assert rec.status == "approval_required"
    assert sink.sends == [], "an unapproved send reached the sink"


def test_the_full_slice_reaches_the_sink_through_the_real_boundary(store, sink,
                                                                   boundary):
    """Durable delegation -> reconstructed actor -> ToolIntent -> boundary ->
    handler dispatch opening the grant -> guarded sink. No test double for the
    boundary, and no grant opened by the scheduled writer."""
    uid = _user(store)
    schedule_occurrence(user_id=uid, job=JOB, action=ACTION, at=AT, store=store)

    def handler(intent, rec):
        sink.send(intent.idempotency_key)
        return {"status": "succeeded", "summary": "sent"}

    boundary.register_handler("local", handler)

    def send(idempotency_key):
        intent = _tool_intent(idempotency_key, current_actor())
        rec = boundary.submit(intent, handler=handler,
                              approval_id=_approve(boundary, intent, current_actor()))
        return {"execution_id": rec.execution_id, "status": rec.status}

    result = execute_scheduled_write(job=JOB, action=ACTION, at=AT, send=send,
                                     store=store)
    assert result.executed, result.reason_code
    assert len(sink.sends) == 1
    assert sink.grants[0].intent_digest, "the sink ran without a correlated grant"
    assert sink.sends[0]["idempotency_key"] == idempotency_key_for(
        occurrence_id(JOB, at=AT), ACTION)


def test_the_boundary_refuses_a_replayed_occurrence_independently(store, sink,
                                                                  boundary):
    """A second layer, keyed on the same identity: even if the claim were
    somehow re-won, the boundary's terminal-replay guard sees the same
    idempotency key and returns the prior record instead of dispatching."""
    uid = _user(store)
    key = idempotency_key_for(occurrence_id(JOB, at=AT), ACTION)

    def handler(intent, rec):
        sink.send(intent.idempotency_key)
        return {"status": "succeeded"}

    boundary.register_handler("local", handler)
    i1 = _tool_intent(key, uid)
    first = boundary.submit(i1, handler=handler, approval_id=_approve(boundary, i1, uid))
    i2 = _tool_intent(key, uid)
    second = boundary.submit(i2, handler=handler, approval_id=_approve(boundary, i2, uid))

    assert len(sink.sends) == 1, "the boundary dispatched a replay"
    assert second.execution_id == first.execution_id


def test_a_different_occurrence_is_dispatched_by_the_boundary(store, sink,
                                                              boundary):
    """Non-vacuity for the test above: the guard must key on identity, not
    refuse everything after the first send."""
    uid = _user(store)

    def handler(intent, rec):
        sink.send(intent.idempotency_key)
        return {"status": "succeeded"}

    boundary.register_handler("local", handler)
    for when in (AT, AT + timedelta(days=1)):
        key = idempotency_key_for(occurrence_id(JOB, at=when), ACTION)
        intent = _tool_intent(key, uid)
        boundary.submit(intent, handler=handler,
                        approval_id=_approve(boundary, intent, uid))
    assert len(sink.sends) == 2


def test_the_boundary_denies_a_mutated_payload_on_the_same_key(store, sink,
                                                               boundary):
    """Digest correlation: the same idempotency key bound to a different action
    is a conflict, not a replay."""
    uid = _user(store)
    key = idempotency_key_for(occurrence_id(JOB, at=AT), ACTION)

    def handler(intent, rec):
        sink.send(intent.idempotency_key)
        return {"status": "succeeded"}

    boundary.register_handler("local", handler)
    intent = _tool_intent(key, uid)
    boundary.submit(intent, handler=handler,
                    approval_id=_approve(boundary, intent, uid))

    mutated = _tool_intent(key, uid)
    object.__setattr__(mutated, "parameters", {"chat_id": "@elsewhere",
                                               "text": "different"})
    rec = boundary.submit(mutated, handler=handler,
                          approval_id=_approve(boundary, mutated, uid))
    assert rec.status == "denied"
    assert rec.failure_category == "idempotency_conflict"
    assert len(sink.sends) == 1


# ── where replay safety lives, pinned ──────────────────────────────────────

def test_replay_safety_is_owned_by_the_claim_and_the_boundary_not_the_stub():
    """`ExecutionGateway.check_idempotency` is still a TODO, and that is the
    correct outcome rather than an outstanding one.

    Replay safety for a scheduled write is owned in two places that already
    exist and are already certified: the atomic delegation claim, and the
    execution boundary's terminal/in-flight guards. Forcing a third
    implementation into the legacy step method would put the same rule in three
    places, and the copy that drifts is the one that leaks.

    What must stay true is that the stub cannot *grant* anything -- it records
    nothing and decides nothing, so an intent it "passes" is still refused by
    everything downstream.
    """
    import inspect

    from saathi.execution.gateway import ExecutionGateway

    source = inspect.getsource(ExecutionGateway.check_idempotency)
    assert "TODO" in source, "if this is implemented, revisit the ownership note"
    # It transitions nothing and returns the history unchanged.
    assert "IntentState.AUTHORIZED" not in source
    assert "add_transition" not in source


def test_the_boundary_owns_the_second_replay_layer():
    """The claim is first; this is the independent second. Both key on the same
    occurrence identity, which is why they cannot disagree."""
    import inspect

    from saathi.execution.universal import UniversalBoundary

    source = inspect.getsource(UniversalBoundary._submit_locked)
    assert "find_by_idempotency" in source
    assert "Terminal replay only when the *same* idempotency_key matches" in source
