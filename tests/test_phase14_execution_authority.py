"""Phase 14 — run creation authority, and the execution authority snapshot.

The snapshot observes authority. It does not grant it, and it is not a token:
`gateway_exec` still enforces independently when execution happens.
"""
import pytest
from fastapi.testclient import TestClient

from saathi.agent_runtime.execution_authority import (
    NOT_APPLICABLE_SOURCES, PRECEDENCE, REASON, AuthorityInputs, AuthorityStatus,
    Provenance, compose, positive)
from saathi.agent_runtime.models import RunState
from saathi.agent_runtime.orchestrator import Orchestrator
from saathi.agent_runtime.store import RunStore
from saathi.security.store import SecurityStore


@pytest.fixture()
def sec(tmp_path):
    from tests.support.auth_state import make_active

    store = SecurityStore(db_path=tmp_path / "security.db")
    make_active(store)
    return store


@pytest.fixture()
def store(tmp_path):
    return RunStore(db_path=tmp_path / "runs.db")


@pytest.fixture()
def orch(store):
    return Orchestrator(store=store, memory=False)


@pytest.fixture()
def client(monkeypatch, sec, store, orch):
    import saathi.agent_runtime.api as api
    import saathi.security.store as secstore
    import saathi.server as server
    from saathi import sessions

    monkeypatch.setattr(api, "default_orchestrator", lambda: orch)
    monkeypatch.setattr(server, "_is_authed", lambda request: True)
    monkeypatch.setattr(secstore, "get_store", lambda: sec)
    monkeypatch.setattr(sessions, "_store", lambda: sec)
    return TestClient(server.app)


def _session(sec, role_id="role-owner") -> str:
    from saathi import sessions

    uid = sec.owner_id()
    with sec.db as db:
        db.execute("DELETE FROM user_roles WHERE user_id=?", (uid,))
        db.execute("INSERT INTO user_roles (user_id, role_id, assigned_at) VALUES (?,?,?)",
                   (uid, role_id, 0))
    return sessions.create(ua="test", ip="127.0.0.1")


def _run(store, orch, *, objective="work"):
    rid = store.create_run(objective=objective, strategy="build", actor="u")
    store.transition(rid, RunState.PLANNING)
    orch._build_tasks(rid, objective, "build", "")
    store.transition(rid, RunState.QUEUED)
    store.transition(rid, RunState.RUNNING)
    return rid


# ══ PART A — create_run authority ══════════════════════════════════════════

def test_unauthenticated_cannot_create_a_run(monkeypatch, store, orch):
    import saathi.agent_runtime.api as api
    import saathi.server as server

    monkeypatch.setattr(api, "default_orchestrator", lambda: orch)
    with TestClient(server.app) as c:
        r = c.post("/api/v1/agents/runs", json={"objective": "x", "strategy": "build"})
    assert r.status_code == 401
    assert store.list_runs(limit=10) == []


def test_a_viewer_cannot_create_a_run(sec, store, orch, client):
    client.headers.update({"x-baadar-session": _session(sec, "role-viewer")})
    r = client.post("/api/v1/agents/runs", json={"objective": "x", "strategy": "build"})
    assert r.status_code == 403
    assert r.json()["error"] == "NOT_AUTHORIZED"
    assert store.list_runs(limit=10) == [], "no run may be created"


def test_a_user_with_no_role_cannot_create_a_run(sec, store, orch, client):
    from saathi import sessions

    uid = sec.owner_id()
    with sec.db as db:
        db.execute("DELETE FROM user_roles WHERE user_id=?", (uid,))
    client.headers.update({"x-baadar-session": sessions.create(ua="t", ip="1.1.1.1")})

    assert client.post("/api/v1/agents/runs",
                       json={"objective": "x", "strategy": "build"}).status_code == 403
    assert store.list_runs(limit=10) == []


def test_an_owner_creates_a_run_recorded_against_them(sec, store, orch, client):
    uid = sec.owner_id()
    client.headers.update({"x-baadar-session": _session(sec, "role-owner")})

    r = client.post("/api/v1/agents/runs", json={"objective": "real work", "strategy": "build"})
    assert r.status_code == 200 and r.json()["ok"] is True

    run = store.get_run(r.json()["run_id"])
    assert run["actor"] == f"user:{uid}", "the creator, not a module default"
    assert "ajay" not in run["actor"]


def test_run_creation_is_audited(sec, store, orch, client):
    uid = sec.owner_id()
    client.headers.update({"x-baadar-session": _session(sec, "role-owner")})
    client.post("/api/v1/agents/runs", json={"objective": "audited", "strategy": "build"})

    rows = [e for e in sec.audit_recent(limit=20) if e["event"] == "run.create"]
    assert rows and rows[0]["user_id"] == uid and rows[0]["ok"] == 1


def test_a_refused_creation_is_audited(sec, store, orch, client):
    client.headers.update({"x-baadar-session": _session(sec, "role-viewer")})
    client.post("/api/v1/agents/runs", json={"objective": "x", "strategy": "build"})

    denied = [e for e in sec.audit_recent(limit=20)
              if e["event"] == "run.create.denied_unauthorized"]
    assert denied and denied[0]["ok"] == 0


def test_creation_audit_carries_no_secret(sec, store, orch, client):
    token = _session(sec, "role-owner")
    client.headers.update({"x-baadar-session": token})
    client.post("/api/v1/agents/runs", json={"objective": "x", "strategy": "build"})

    blob = str([e for e in sec.audit_recent(limit=20) if e["event"].startswith("run.create")])
    assert token not in blob
    for secret in ("password", "cookie", "authorization"):
        assert secret not in blob.lower()


def test_permission_to_create_does_not_unlock_a_fixture(monkeypatch, sec, store, orch, client):
    """RBAC and fixture gating are independent gates.

    An owner has every permission and still cannot reach a certification
    strategy while its environment gate is disarmed.
    """
    from saathi.agent_runtime.test_authority import AUTHORITY_ENV

    monkeypatch.delenv(AUTHORITY_ENV, raising=False)
    client.headers.update({"x-baadar-session": _session(sec, "role-owner")})

    r = client.post("/api/v1/agents/runs",
                    json={"objective": "x", "strategy": "test_approval"})
    assert r.status_code == 200, "authorised, so not a 403"
    run = store.get_run(r.json()["run_id"])
    assert run["strategy"] != "test_approval", "the fixture stayed out of reach"


# ══ PART B — the composer ══════════════════════════════════════════════════

def _ok_inputs(**over) -> AuthorityInputs:
    """Inputs where every gate passes, so a test can spoil exactly one."""
    base = dict(
        actor_user_id="u1", has_permission=True,
        run={"state": RunState.RUNNING.value},
        pending_approvals=[], resolved_approvals=[],
        kill_switch_blocked=False, platform_runtime_bound=True,
        now=1000.0,
    )
    base.update(over)
    return AuthorityInputs(**base)


def test_the_baseline_inputs_reach_the_positive_state():
    snap = compose(_ok_inputs(), run_id="r1")
    assert snap["status"] == AuthorityStatus.AUTHORITY_CHECKS_PASSED.value
    assert positive(snap) is True
    assert snap["blocking"] == []


def test_the_positive_state_is_the_weakest_truthful_claim():
    # Deliberately not EXECUTION_ALLOWED / SAFE_TO_EXECUTE: the checks passing
    # is not a promise that execution would succeed.
    names = {s.value for s in AuthorityStatus}
    for overclaim in ("EXECUTION_ALLOWED", "SAFE_TO_EXECUTE", "READY_TO_TRADE",
                      "AUTHORIZED_EXECUTION", "GUARANTEED"):
        assert overclaim not in names
    assert AuthorityStatus.AUTHORITY_CHECKS_PASSED.value == "AUTHORITY_CHECKS_PASSED"


@pytest.mark.parametrize("spoil,expected", [
    ({"kill_switch_blocked": True}, AuthorityStatus.KILL_SWITCH_ACTIVE),
    ({"actor_user_id": None}, AuthorityStatus.NOT_AUTHENTICATED),
    ({"has_permission": False}, AuthorityStatus.NOT_AUTHORIZED),
    ({"run": None}, AuthorityStatus.ACTION_UNKNOWN),
    ({"run": {"state": RunState.COMPLETED.value}}, AuthorityStatus.RUN_STATE_BLOCKS),
    ({"run": {"state": RunState.BLOCKED.value}}, AuthorityStatus.RUN_STATE_BLOCKS),
    ({"platform_runtime_bound": False}, AuthorityStatus.PLATFORM_RUNTIME_UNAVAILABLE),
])
def test_each_gate_blocks_on_its_own(spoil, expected):
    snap = compose(_ok_inputs(**spoil), run_id="r1")
    assert snap["status"] == expected.value
    assert positive(snap) is False


def test_a_pending_approval_waits():
    snap = compose(_ok_inputs(pending_approvals=[{"id": "a1", "expires_at": 9999.0}]))
    assert snap["status"] == AuthorityStatus.WAITING_APPROVAL.value
    assert snap["provenance"] == Provenance.APPROVAL_STORE.value


def test_an_expired_pending_approval_is_expired_not_waiting():
    snap = compose(_ok_inputs(pending_approvals=[{"id": "a1", "expires_at": 10.0}]))
    assert snap["status"] == AuthorityStatus.APPROVAL_EXPIRED.value


def test_a_denied_approval_blocks():
    snap = compose(_ok_inputs(resolved_approvals=[{"id": "a1", "status": "denied"}]))
    assert snap["status"] == AuthorityStatus.APPROVAL_DENIED.value


def test_approval_granted_is_not_execution_permission():
    """The rule this milestone exists to keep.

    An approved approval merely stops blocking here; every other gate still
    applies, and one of them failing keeps the snapshot negative.
    """
    snap = compose(_ok_inputs(
        resolved_approvals=[{"id": "a1", "status": "approved"}],
        platform_runtime_bound=False))
    assert snap["status"] == AuthorityStatus.PLATFORM_RUNTIME_UNAVAILABLE.value
    assert positive(snap) is False


# ── unknown fails closed ───────────────────────────────────────────────────

@pytest.mark.parametrize("unknown", [
    {"kill_switch_blocked": None},
    {"platform_runtime_bound": None},
    {"has_permission": None},
    {"run": {"state": "not-a-real-state"}},
])
def test_an_unestablished_input_can_never_be_positive(unknown):
    snap = compose(_ok_inputs(**unknown), run_id="r1")
    assert positive(snap) is False, "unknown must fail closed"


def test_unknown_outranks_the_positive_state():
    from saathi.agent_runtime.execution_authority import _RANK

    assert _RANK[AuthorityStatus.UNKNOWN] < _RANK[AuthorityStatus.AUTHORITY_CHECKS_PASSED]


# ── precedence ─────────────────────────────────────────────────────────────

def test_the_kill_switch_dominates_everything():
    # Approved, authorised, healthy, running -- and still stopped.
    snap = compose(_ok_inputs(
        kill_switch_blocked=True,
        resolved_approvals=[{"id": "a1", "status": "approved"}]))
    assert snap["status"] == AuthorityStatus.KILL_SWITCH_ACTIVE.value


def test_authorisation_outranks_the_actions_own_state():
    # A caller who may not act should not be told the action is merely waiting.
    snap = compose(_ok_inputs(has_permission=False,
                              pending_approvals=[{"id": "a1"}]))
    assert snap["status"] == AuthorityStatus.NOT_AUTHORIZED.value


def test_run_state_outranks_approval():
    snap = compose(_ok_inputs(run={"state": RunState.COMPLETED.value},
                              pending_approvals=[{"id": "a1"}]))
    assert snap["status"] == AuthorityStatus.RUN_STATE_BLOCKS.value


def test_precedence_is_total_and_positive_is_last():
    assert len(set(PRECEDENCE)) == len(PRECEDENCE), "no duplicates"
    assert set(PRECEDENCE) == set(AuthorityStatus), "every state is ordered"
    assert PRECEDENCE[-1] is AuthorityStatus.AUTHORITY_CHECKS_PASSED


def test_everything_blocking_is_reported_not_just_the_strongest():
    snap = compose(_ok_inputs(kill_switch_blocked=True, has_permission=False,
                              platform_runtime_bound=False))
    statuses = [b["status"] for b in snap["blocking"]]
    assert AuthorityStatus.KILL_SWITCH_ACTIVE.value in statuses
    assert AuthorityStatus.NOT_AUTHORIZED.value in statuses
    assert AuthorityStatus.PLATFORM_RUNTIME_UNAVAILABLE.value in statuses
    assert snap["status"] == statuses[0], "the strongest is reported as the status"


# ── provenance and honesty about silence ───────────────────────────────────

def test_every_status_names_a_reason_code_and_source():
    for status in AuthorityStatus:
        assert status in REASON and "." in REASON[status]


def test_subsystems_that_cannot_speak_say_so():
    """Guardian and the gateway scaffold are recorded as silent, not as passes."""
    snap = compose(_ok_inputs())
    assert "trading_guardian" in snap["not_applicable"]
    assert "execution_gateway" in snap["not_applicable"]
    assert "trading" in snap["not_applicable"]["trading_guardian"]
    assert "unimplemented" in snap["not_applicable"]["execution_gateway"]


def test_the_gateway_stub_never_contributes_a_pass():
    """`ExecutionGateway.authorize` grants unconditionally with a TODO.

    If it is ever implemented this test should be revisited -- until then it must
    not appear as an authority source at all.
    """
    from saathi.agent_runtime import execution_authority as ea

    assert not any("execution_gateway" in str(p.value).lower() for p in Provenance)
    assert "execution_gateway" in ea.NOT_APPLICABLE_SOURCES


# ── correlation, read-only, non-token ──────────────────────────────────────

def test_a_snapshot_is_about_one_action_not_the_system():
    snap = compose(_ok_inputs(), run_id="r1", task_id="t1")
    assert snap["run_id"] == "r1" and snap["task_id"] == "t1"
    # No global "SaathiOS can execute" field exists.
    assert not any(k in snap for k in ("can_execute", "allowed", "execution_allowed"))


def test_a_snapshot_carries_no_capability_semantics():
    snap = compose(_ok_inputs())
    assert snap["is_capability_token"] is False
    assert snap["read_only"] is True
    blob = str(snap).lower()
    for secret in ("token=", "signature", "bearer", "secret", "credential"):
        assert secret not in blob


def test_composition_mutates_nothing(store, orch):
    rid = _run(store, orch)
    before = dict(store.get_run(rid))
    tasks_before = [dict(t) for t in store.list_tasks(rid)]

    compose(_ok_inputs(run=store.get_run(rid)), run_id=rid)

    assert dict(store.get_run(rid)) == before
    assert [dict(t) for t in store.list_tasks(rid)] == tasks_before


# ── the endpoint ───────────────────────────────────────────────────────────

def test_the_snapshot_endpoint_requires_authentication(monkeypatch, store, orch):
    import saathi.agent_runtime.api as api
    import saathi.server as server

    monkeypatch.setattr(api, "default_orchestrator", lambda: orch)
    rid = _run(store, orch)
    with TestClient(server.app) as c:
        r = c.get(f"/api/v1/agents/runs/{rid}/execution-authority")
    assert r.status_code == 401


def test_the_snapshot_explains_rather_than_withholds(sec, store, orch, client):
    """A read-only explanation is the point, so an unauthorised reader is told
    why they cannot act rather than being refused the answer."""
    rid = _run(store, orch)
    client.headers.update({"x-baadar-session": _session(sec, "role-viewer")})

    r = client.get(f"/api/v1/agents/runs/{rid}/execution-authority")
    assert r.status_code == 200
    assert r.json()["status"] == AuthorityStatus.NOT_AUTHORIZED.value
    assert r.json()["reason_code"] == "rbac.permission_missing"


def test_an_unknown_run_is_action_unknown(sec, store, orch, client):
    client.headers.update({"x-baadar-session": _session(sec, "role-owner")})
    r = client.get("/api/v1/agents/runs/no-such-run/execution-authority")
    assert r.status_code == 200
    assert r.json()["status"] == AuthorityStatus.ACTION_UNKNOWN.value


def test_the_endpoint_mutates_nothing(sec, store, orch, client):
    rid = _run(store, orch)
    before = dict(store.get_run(rid))
    client.headers.update({"x-baadar-session": _session(sec, "role-owner")})

    client.get(f"/api/v1/agents/runs/{rid}/execution-authority")
    client.get(f"/api/v1/agents/runs/{rid}/execution-authority")

    assert dict(store.get_run(rid)) == before
    assert store.pending_approvals(rid) == []


def test_the_snapshot_reflects_a_change_between_reads(sec, store, orch, client):
    """No cached positive authority: a later snapshot must show a new restriction."""
    rid = _run(store, orch)
    client.headers.update({"x-baadar-session": _session(sec, "role-owner")})

    first = client.get(f"/api/v1/agents/runs/{rid}/execution-authority").json()
    store.transition(rid, RunState.CANCELLED)
    second = client.get(f"/api/v1/agents/runs/{rid}/execution-authority").json()

    assert second["status"] == AuthorityStatus.RUN_STATE_BLOCKS.value
    assert positive(second) is False
    assert first["evaluated_at"] <= second["evaluated_at"]


def test_snapshots_do_not_leak_across_runs(sec, store, orch, client):
    a = _run(store, orch, objective="a")
    b = _run(store, orch, objective="b")
    store.transition(b, RunState.CANCELLED)
    client.headers.update({"x-baadar-session": _session(sec, "role-owner")})

    sa = client.get(f"/api/v1/agents/runs/{a}/execution-authority").json()
    sb = client.get(f"/api/v1/agents/runs/{b}/execution-authority").json()

    assert sa["run_id"] == a and sb["run_id"] == b
    assert sb["status"] == AuthorityStatus.RUN_STATE_BLOCKS.value
    assert sa["status"] != sb["status"], "one run's verdict is not another's"


# ── invariants ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("blocker", [
    {"kill_switch_blocked": True},
    {"has_permission": False},
    {"actor_user_id": None},
    {"run": None},
    {"run": {"state": RunState.FAILED.value}},
    {"pending_approvals": [{"id": "a1"}]},
    {"resolved_approvals": [{"id": "a1", "status": "denied"}]},
    {"platform_runtime_bound": False},
    {"kill_switch_blocked": None},
    {"platform_runtime_bound": None},
])
def test_invariant_any_blocker_makes_a_positive_result_impossible(blocker):
    assert positive(compose(_ok_inputs(**blocker))) is False
