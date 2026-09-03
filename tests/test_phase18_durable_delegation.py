"""Phase 18 — a background job must not become anonymous authority.

Phase 17 bound the authenticated user for the life of a request. Work that
outlives the request cannot use that, so it reached the gateway with no identity
and fell back to the constrained system actor: safe, but anonymous, and
anonymous work cannot be attributed, revoked, or held to the permissions its
originator actually has.

The decisive test in this file is `test_a_worker_with_no_request_context_...`:
a thread that never saw the request rebuilds the real user from a durable
record, and gives it back afterwards. Everything else exists to stop that
mechanism becoming a way to hold authority the user no longer has.

No live trading, no broker, no external write anywhere in this file.
"""
from __future__ import annotations

import concurrent.futures
import threading
import time

import pytest

from saathi.agent_runtime.contracts import AuthorityClass
from saathi.execution.authorization_sources import actor_context, current_actor
from saathi.execution.delegated_work import (
    SCOPE_JOB,
    create_job_delegation,
    execute_delegated,
)
from saathi.execution.delegation import (
    DEFAULT_TTL_SEC,
    DelegationRequest,
    DelegationStatus,
    evaluate,
    resolve,
    status_of,
)
from saathi.security.store import SecurityStore


# ── fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture()
def store(tmp_path):
    from tests.support.auth_state import make_active

    s = SecurityStore(db_path=tmp_path / "security.db")
    make_active(s)
    return s


def _user(store, name: str, *, role: str = "role-owner") -> str:
    """A real user in the store, with a real role. Not a stand-in."""
    owner = store.owner_id()
    if name == "owner":
        uid = owner
    else:
        uid = f"u_{name}"
        now = time.time()
        store.db.execute(
            "INSERT OR IGNORE INTO users (id, email, name, status, created_at, updated_at)"
            " VALUES (?,?,?,'active',?,?)", (uid, f"{name}@example.com", name, now, now))
    store.db.execute("DELETE FROM user_roles WHERE user_id=?", (uid,))
    if role:
        store.db.execute(
            "INSERT INTO user_roles (user_id, role_id, assigned_at) VALUES (?,?,?)",
            (uid, role, 0))
    store.db.commit()
    return uid


def _delegate(store, uid, *, job="nightly", ceiling=AuthorityClass.READ_ONLY.value,
              ttl=3600.0, max_uses=1) -> str:
    return store.create_delegation(
        user_id=uid, scope_kind=SCOPE_JOB, scope_ref=job, action=job,
        authority_ceiling=ceiling, ttl_sec=ttl, max_uses=max_uses)


def _request(delegation_id, *, job="nightly",
             authority=AuthorityClass.READ_ONLY.value) -> DelegationRequest:
    return DelegationRequest(delegation_id=delegation_id, scope_kind=SCOPE_JOB,
                             scope_ref=job, action=job, authority_class=authority)


# ── the baseline is genuinely positive ──────────────────────────────────────

def test_a_valid_delegation_resolves_to_its_originating_user(store):
    """Otherwise every refusal below would pass for the wrong reason."""
    uid = _user(store, "owner")
    decision = resolve(_delegate(store, uid), _request("x"), store=store)
    # The request id is ignored in favour of the one being resolved.
    decision = resolve(_delegate(store, uid), _request(""), store=store)
    assert decision.reason_code == "delegation.scope_mismatch" or not decision.valid

    did = _delegate(store, uid)
    ok = resolve(did, _request(did), store=store)
    assert ok.valid and ok.user_id == uid
    assert ok.authority_ceiling == AuthorityClass.READ_ONLY.value


# ── the decisive property ───────────────────────────────────────────────────

def test_a_worker_with_no_request_context_rebuilds_the_real_user(store):
    """The whole point of the milestone.

    A thread that never saw the authenticated request runs as the user who
    authorized the work -- and gives the identity back afterwards, so whatever
    the thread does next is anonymous again.
    """
    uid = _user(store, "owner")
    did = _delegate(store, uid)
    seen: dict = {}

    def job():
        seen["actor"] = current_actor()

    assert current_actor() is None, "no ambient identity to leak in"
    worker = threading.Thread(
        target=lambda: execute_delegated(did, _request(did), job, store=store))
    worker.start()
    worker.join()

    assert seen["actor"] == uid, "the worker must act as the originating user"
    assert current_actor() is None, "and must not leave that identity behind"


def test_the_worker_resets_the_actor_even_when_the_job_raises(store):
    uid = _user(store, "owner")
    did = _delegate(store, uid)
    inner: dict = {}

    def boom():
        inner["actor"] = current_actor()
        raise RuntimeError("job failed")

    with pytest.raises(RuntimeError):
        execute_delegated(did, _request(did), boom, store=store)
    assert inner["actor"] == uid
    assert current_actor() is None


def test_a_refused_delegation_binds_nobody(store):
    """A refusal must leave the constrained system actor in place, not proceed
    as somebody."""
    uid = _user(store, "owner")
    did = _delegate(store, uid)
    store.revoke_delegation(did)
    seen: dict = {"ran": False}

    def job():
        seen["ran"] = True

    decision, _ = execute_delegated(did, _request(did), job, store=store)
    assert not decision.valid and seen["ran"] is False
    assert current_actor() is None


def test_a_system_task_after_a_delegated_one_does_not_inherit_the_user(store):
    uid = _user(store, "owner")
    execute_delegated(_delegate(store, uid), _request(_delegate(store, uid)),
                      lambda: None, store=store)
    seen: dict = {}
    threading.Thread(target=lambda: seen.setdefault("actor", current_actor())).start()
    time.sleep(0.05)
    assert seen.get("actor") is None


# ── no session material is persisted ────────────────────────────────────────

def test_the_delegation_record_holds_no_credential(store):
    """A session is authentication material. Re-presenting one later is
    impersonation, not delegation."""
    uid = _user(store, "owner")
    record = store.get_delegation(_delegate(store, uid))
    for forbidden in ("token", "session", "cookie", "password", "authorization",
                      "secret", "credential"):
        assert not any(forbidden in str(k).lower() for k in record), forbidden


def test_the_delegation_schema_stores_no_secret_columns(store):
    cols = {r[1].lower() for r in
            store.db.execute("PRAGMA table_info(authority_delegation)").fetchall()}
    assert cols == {"delegation_id", "user_id", "scope_kind", "scope_ref", "action",
                    "authority_ceiling", "created_at", "expires_at", "max_uses",
                    "used", "revoked_at"}


# ── a delegation id is not a bearer token ───────────────────────────────────

def test_knowing_a_delegation_id_authorizes_nothing_by_itself(store):
    """Every field is re-read from the canonical record; the id is a lookup key,
    not a credential."""
    uid = _user(store, "owner")
    did = _delegate(store, uid)
    # Right id, wrong work.
    wrong = DelegationRequest(delegation_id=did, scope_kind=SCOPE_JOB,
                              scope_ref="some-other-job", action="nightly")
    assert resolve(did, wrong, store=store).reason_code == "delegation.scope_mismatch"


def test_a_decision_declares_it_is_not_a_capability_token(store):
    uid = _user(store, "owner")
    did = _delegate(store, uid)
    assert resolve(did, _request(did), store=store).to_dict()["is_capability_token"] is False


def test_an_unknown_delegation_id_is_refused(store):
    assert resolve("dlg_nonexistent", _request("dlg_nonexistent"),
                   store=store).reason_code == "delegation.unknown"


def test_no_delegation_id_at_all_is_refused(store):
    assert resolve("", _request(""), store=store).reason_code == "delegation.missing"


# ── correlation: cross-user, cross-scope, cross-action ──────────────────────

def test_one_users_delegation_does_not_authorize_another_user(store):
    """The canonical record decides origin. There is no caller-supplied user id
    to change."""
    alice = _user(store, "alice")
    _user(store, "bob")
    did = _delegate(store, alice)
    decision = resolve(did, _request(did), store=store)
    assert decision.valid and decision.user_id == alice
    assert decision.user_id != "u_bob"


def test_a_delegation_for_one_job_does_not_authorize_another(store):
    uid = _user(store, "owner")
    did = _delegate(store, uid, job="backup")
    other = _request(did, job="autopost")
    assert resolve(did, other, store=store).reason_code == "delegation.scope_mismatch"


def test_a_delegation_bound_to_a_run_does_not_authorize_a_job(store):
    uid = _user(store, "owner")
    did = store.create_delegation(user_id=uid, scope_kind="run", scope_ref="r1",
                                  action="r1", authority_ceiling="READ_ONLY",
                                  ttl_sec=3600, max_uses=1)
    assert resolve(did, _request(did, job="r1"),
                   store=store).reason_code == "delegation.scope_mismatch"


def test_the_action_must_match_not_only_the_scope(store):
    uid = _user(store, "owner")
    did = store.create_delegation(user_id=uid, scope_kind=SCOPE_JOB, scope_ref="nightly",
                                  action="backup", authority_ceiling="READ_ONLY",
                                  ttl_sec=3600, max_uses=1)
    assert resolve(did, _request(did),
                   store=store).reason_code == "delegation.action_mismatch"


# ── authority ceiling ───────────────────────────────────────────────────────

def test_a_delegation_cannot_authorize_above_its_ceiling(store):
    uid = _user(store, "owner")
    did = _delegate(store, uid, ceiling=AuthorityClass.READ_ONLY.value)
    escalated = _request(did, authority=AuthorityClass.EXTERNAL_MUTATION.value)
    assert resolve(did, escalated,
                   store=store).reason_code == "delegation.ceiling_exceeded"


def test_an_action_at_or_below_the_ceiling_is_allowed(store):
    uid = _user(store, "owner")
    did = _delegate(store, uid, ceiling=AuthorityClass.EXTERNAL_MUTATION.value)
    for wanted in (AuthorityClass.READ_ONLY.value,
                   AuthorityClass.LOCAL_MUTATION.value,
                   AuthorityClass.EXTERNAL_MUTATION.value):
        assert resolve(did, _request(did, authority=wanted), store=store).valid, wanted


def test_an_unrecognised_authority_class_is_refused_not_ranked(store):
    uid = _user(store, "owner")
    did = _delegate(store, uid)
    assert resolve(did, _request(did, authority="SUPER_ADMIN"),
                   store=store).reason_code == "delegation.ceiling_exceeded"


def test_financial_execution_can_never_be_a_ceiling(store):
    """It is prohibited outright at the gateway; a delegation must not be able
    to carry it either."""
    uid = _user(store, "owner")
    did = _delegate(store, uid, ceiling=AuthorityClass.FINANCIAL_EXECUTION.value)
    assert resolve(did, _request(did, authority=AuthorityClass.FINANCIAL_EXECUTION.value),
                   store=store).reason_code == "delegation.ceiling_exceeded"


# ── live RBAC, not a snapshot ───────────────────────────────────────────────

def test_losing_the_role_invalidates_an_existing_delegation(store):
    """A job must not quietly outrank the person who scheduled it."""
    uid = _user(store, "owner")
    did = _delegate(store, uid)
    assert resolve(did, _request(did), store=store).valid

    store.db.execute("DELETE FROM user_roles WHERE user_id=?", (uid,))
    store.db.commit()
    assert resolve(did, _request(did),
                   store=store).reason_code == "delegation.rbac_revoked"


def test_restoring_the_role_makes_an_otherwise_valid_delegation_work_again(store):
    uid = _user(store, "owner")
    did = _delegate(store, uid)
    store.db.execute("DELETE FROM user_roles WHERE user_id=?", (uid,))
    store.db.commit()
    assert not resolve(did, _request(did), store=store).valid
    _user(store, "owner")  # reassigns the role
    assert resolve(did, _request(did), store=store).valid


def test_a_viewer_role_cannot_hold_a_delegation(store):
    """Delegation uses the same permission the interactive path requires, so it
    cannot become a way to act with permissions a live request would refuse."""
    uid = _user(store, "viewer", role="role-viewer")
    did = _delegate(store, uid)
    assert resolve(did, _request(did),
                   store=store).reason_code == "delegation.rbac_revoked"


def test_a_disabled_user_cannot_hold_a_delegation(store):
    """A durable job must not become ownerless authority."""
    uid = _user(store, "owner")
    did = _delegate(store, uid)
    store.db.execute("UPDATE users SET status='disabled' WHERE id=?", (uid,))
    store.db.commit()
    assert resolve(did, _request(did),
                   store=store).reason_code == "delegation.user_unavailable"


def test_a_user_with_live_delegations_cannot_be_silently_deleted(store):
    """The foreign key makes orphaning impossible rather than merely unlikely:
    deleting the originating user is refused while a delegation points at them,
    so a durable job cannot quietly become ownerless authority."""
    import sqlite3

    uid = _user(store, "alice")
    _delegate(store, uid)
    store.db.execute("DELETE FROM user_roles WHERE user_id=?", (uid,))
    with pytest.raises(sqlite3.IntegrityError):
        store.db.execute("DELETE FROM users WHERE id=?", (uid,))
        store.db.commit()
    store.db.rollback()


def test_a_delegation_whose_user_is_gone_resolves_to_nobody(store):
    """The FK is one defence; the resolver is the other. Revoking first is the
    supported deletion path, and a record that outlives its user still refuses."""
    uid = _user(store, "alice")
    did = _delegate(store, uid)
    store.db.execute("DELETE FROM authority_delegation WHERE user_id=?", (uid,))
    store.db.execute("DELETE FROM user_roles WHERE user_id=?", (uid,))
    store.db.execute("DELETE FROM users WHERE id=?", (uid,))
    store.db.commit()
    assert resolve(did, _request(did), store=store).reason_code == "delegation.unknown"


# ── expiry and revocation ───────────────────────────────────────────────────

def test_an_expired_delegation_is_refused(store):
    uid = _user(store, "owner")
    did = _delegate(store, uid, ttl=-1.0)  # already past
    assert resolve(did, _request(did), store=store).reason_code == "delegation.expired"


def test_expiry_is_evaluated_against_a_supplied_clock_not_a_sleep(store):
    uid = _user(store, "owner")
    did = _delegate(store, uid, ttl=100.0)
    record = store.get_delegation(did)
    assert status_of(record, now=record["created_at"] + 1) is DelegationStatus.ACTIVE
    assert status_of(record, now=record["created_at"] + 101) is DelegationStatus.EXPIRED


def test_a_revoked_delegation_is_refused(store):
    uid = _user(store, "owner")
    did = _delegate(store, uid)
    assert store.revoke_delegation(did) is True
    assert resolve(did, _request(did), store=store).reason_code == "delegation.revoked"


def test_revoking_twice_is_not_a_second_revocation(store):
    uid = _user(store, "owner")
    did = _delegate(store, uid)
    assert store.revoke_delegation(did) is True
    assert store.revoke_delegation(did) is False


def test_cancelling_the_parent_work_revokes_its_delegations(store):
    """A delegation exists to authorize particular work; it should not outlive
    it. Cancelling the parent is the natural revocation gesture."""
    uid = _user(store, "owner")
    first = _delegate(store, uid, job="nightly")
    second = _delegate(store, uid, job="nightly")
    other = _delegate(store, uid, job="backup")

    assert store.revoke_delegations_for_scope(SCOPE_JOB, "nightly") == 2
    for did in (first, second):
        assert resolve(did, _request(did), store=store).reason_code == "delegation.revoked"
    assert resolve(other, _request(other, job="backup"), store=store).valid


# ── one-shot and reuse ──────────────────────────────────────────────────────

def test_a_one_shot_delegation_cannot_be_used_twice(store):
    uid = _user(store, "owner")
    did = _delegate(store, uid)
    runs = []
    first, _ = execute_delegated(did, _request(did), lambda: runs.append(1), store=store)
    second, _ = execute_delegated(did, _request(did), lambda: runs.append(2), store=store)
    assert first.valid and not second.valid
    assert second.reason_code == "delegation.exhausted"
    assert runs == [1], "the refused attempt must not have run the work"


def test_a_multi_use_delegation_is_bounded_by_its_count(store):
    uid = _user(store, "owner")
    did = _delegate(store, uid, max_uses=3)
    outcomes = [execute_delegated(did, _request(did), lambda: None, store=store)[0].valid
                for _ in range(4)]
    assert outcomes == [True, True, True, False]


def test_one_shot_is_the_default(store):
    """A delegation authorizing unbounded future executions is a standing grant
    wearing a delegation's name; asking for that has to be explicit."""
    uid = _user(store, "owner")
    assert store.get_delegation(_delegate(store, uid))["max_uses"] == 1


# ── concurrency: exactly one winner ─────────────────────────────────────────

def test_racing_workers_cannot_both_claim_a_one_shot_delegation(store):
    """The guard is in the UPDATE's WHERE clause, not a read followed by a
    write, so two workers cannot both observe a free use."""
    uid = _user(store, "owner")
    did = _delegate(store, uid)
    barrier = threading.Barrier(8)

    def claim():
        barrier.wait()
        return store.consume_delegation(did)

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        results = [f.result() for f in [pool.submit(claim) for _ in range(8)]]
    assert results.count(True) == 1, results


def test_racing_executions_run_the_work_exactly_once(store):
    uid = _user(store, "owner")
    did = _delegate(store, uid)
    ran = []
    barrier = threading.Barrier(6)

    def attempt():
        barrier.wait()
        return execute_delegated(did, _request(did), lambda: ran.append(1), store=store)[0]

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        decisions = [f.result() for f in [pool.submit(attempt) for _ in range(6)]]
    assert len(ran) == 1
    assert sum(1 for d in decisions if d.valid) == 1


# ── the pure evaluator, exhaustively ────────────────────────────────────────

def _record(**over) -> dict:
    base = {"delegation_id": "dlg_1", "user_id": "u1", "scope_kind": SCOPE_JOB,
            "scope_ref": "nightly", "action": "nightly",
            "authority_ceiling": AuthorityClass.READ_ONLY.value,
            "created_at": 1000.0, "expires_at": 2000.0, "max_uses": 1,
            "used": 0, "revoked_at": None}
    base.update(over)
    return base


_ACTIVE_USER = {"id": "u1", "status": "active"}


def test_the_evaluator_is_positive_on_a_complete_valid_input():
    decision = evaluate(_record(), _request("dlg_1"), user=_ACTIVE_USER,
                        has_permission=True, now=1500.0)
    assert decision.valid and decision.user_id == "u1"


@pytest.mark.parametrize("kwargs,reason", [
    ({"user": None, "has_permission": True}, "delegation.user_unavailable"),
    ({"user": {"status": "disabled"}, "has_permission": True}, "delegation.user_unavailable"),
    ({"user": _ACTIVE_USER, "has_permission": False}, "delegation.rbac_revoked"),
    ({"user": _ACTIVE_USER, "has_permission": None}, "delegation.rbac_revoked"),
])
def test_any_unestablished_identity_input_refuses(kwargs, reason):
    """None means could-not-establish and must never read as satisfied."""
    assert evaluate(_record(), _request("dlg_1"), now=1500.0, **kwargs).reason_code == reason


def test_a_missing_record_refuses():
    assert evaluate(None, _request("dlg_1"), user=_ACTIVE_USER,
                    has_permission=True).reason_code == "delegation.unknown"


# ── delegation does not replace the gateway ─────────────────────────────────

def test_delegation_grants_nothing_the_gateway_would_refuse(store):
    """A delegation is an identity input. Every Phase 16 gate still runs, and a
    dominant one still dominates."""
    from saathi.execution.authorization import (
        AuthorizationInputs, Decision, authorize_intent)
    from saathi.execution.toolintent import ToolIntent

    uid = _user(store, "owner")
    did = _delegate(store, uid)
    decision = resolve(did, _request(did), store=store)
    assert decision.valid

    intent = ToolIntent(intent_id="p18", operation="local-llm-inference",
                        actor_id=f"user:{decision.user_id}", parameters={"p": 1})
    blocked = AuthorizationInputs(actor_user_id=decision.user_id, has_permission=True,
                                  kill_switch_blocked=True, approvals=[], now=1_000_000.0)
    assert authorize_intent(intent, blocked).decision is Decision.DENIED
    assert authorize_intent(intent, blocked).reason_code == "kill_switch.active"


def test_a_delegation_created_before_a_kill_switch_does_not_bypass_it(store):
    """Delegation is older than the stop; the stop still wins."""
    from saathi.execution.authorization import (
        AuthorizationInputs, Decision, authorize_intent)
    from saathi.execution.toolintent import ToolIntent

    uid = _user(store, "owner")
    did = _delegate(store, uid)
    intent = ToolIntent(intent_id="p18-ks", operation="local-llm-inference",
                        actor_id=f"user:{uid}", parameters={})
    with actor_context(resolve(did, _request(did), store=store).user_id):
        inputs = AuthorizationInputs(actor_user_id=uid, has_permission=True,
                                     kill_switch_blocked=True, approvals=[],
                                     now=1_000_000.0)
        assert authorize_intent(intent, inputs).decision is Decision.DENIED


def test_a_delegation_does_not_pre_approve_sensitive_actions(store):
    """"The user started this job" is not "the user approved everything it may
    later attempt." The approval gate is untouched."""
    from saathi.execution.authorization import (
        AuthorizationInputs, Decision, authorize_intent)
    from saathi.execution.toolintent import ToolIntent

    uid = _user(store, "owner")
    intent = ToolIntent(intent_id="p18-appr", operation="video-generation",
                        actor_id=f"user:{uid}", parameters={})
    inputs = AuthorizationInputs(actor_user_id=uid, has_permission=True,
                                 kill_switch_blocked=False, approvals=[],
                                 now=1_000_000.0)
    result = authorize_intent(intent, inputs)
    assert result.decision is Decision.DENIED
    assert result.reason_code == "approval.missing"


# ── audit ───────────────────────────────────────────────────────────────────

def test_use_and_refusal_are_both_audited(store):
    uid = _user(store, "owner")
    did = _delegate(store, uid)
    execute_delegated(did, _request(did), lambda: None, store=store)
    execute_delegated(did, _request(did), lambda: None, store=store)  # exhausted

    events = [e["event"] for e in store.audit_recent(limit=20)]
    assert "delegation.used" in events
    assert "delegation.denied" in events


def test_the_audit_trail_names_identifiers_not_secrets(store):
    uid = _user(store, "owner")
    did = _delegate(store, uid)
    execute_delegated(did, _request(did), lambda: None, store=store)
    blob = str(store.audit_recent(limit=10))
    assert did[:16] in blob
    for forbidden in ("password", "cookie", "bearer ", "x-baadar-session"):
        assert forbidden not in blob.lower()


# ── background output is sanitised like everything else ─────────────────────

def test_a_secret_in_delegated_output_is_redacted(store):
    """Running in the background is not a way around the Phase 17 boundary."""
    from saathi.execution.sanitization import sanitize

    uid = _user(store, "owner")
    did = _delegate(store, uid)
    fake = "sk-abcdefghijklmnop1234567890"

    def job():
        return {"log": f"used {fake}", "password": "hunter2", "kept": "ordinary"}

    _, raw = execute_delegated(did, _request(did), job, store=store)
    cleaned, report = sanitize(raw)
    assert fake not in str(cleaned) and "hunter2" not in str(cleaned)
    assert cleaned["kept"] == "ordinary"
    assert report.redaction_count == 2


# ── the substrate does not invent identity ──────────────────────────────────

def test_no_user_means_no_delegation_rather_than_a_fabricated_one(store):
    """Anonymous work stays anonymous, and therefore stays capped."""
    assert create_job_delegation(user_id="", job_name="nightly", store=store) == ""


def test_the_delegation_module_never_reads_a_request():
    """Identity comes from the durable record and the store, never from a
    payload, header or caller claim."""
    import ast
    import pathlib

    # Parsed, not grepped. Both modules' docstrings discuss "the request" at
    # length -- a substring search flags the explanation rather than any code.
    for path in ("saathi/execution/delegation.py",
                 "saathi/execution/delegated_work.py"):
        tree = ast.parse(pathlib.Path(path).read_text())
        docstrings = {id(n.value) for n in ast.walk(tree)
                      if isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)}
        attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        literals = {n.value for n in ast.walk(tree)
                    if isinstance(n, ast.Constant) and isinstance(n.value, str)
                    and id(n) not in docstrings}
        for forbidden in ("headers", "cookies", "json", "body"):
            assert forbidden not in attrs, f"{path} reads .{forbidden}"
            assert forbidden not in names, f"{path} uses {forbidden}"
            assert forbidden not in literals, f"{path} names {forbidden!r}"


def test_the_default_lifetime_is_bounded():
    assert 0 < DEFAULT_TTL_SEC <= 24 * 3600
