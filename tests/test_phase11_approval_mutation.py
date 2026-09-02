"""Phase 11 — the approval mutation contract.

Approval is permission to continue one authority step. It is not execution, not
Guardian clearance and not ExecutionGateway permission, and the route that grants
it has to bind to exactly one approval on exactly one run.
"""
import pytest
from fastapi.testclient import TestClient

from saathi.agent_runtime import strategies
from saathi.agent_runtime.models import RunState
from saathi.agent_runtime.orchestrator import Orchestrator
from saathi.agent_runtime.store import RunStore
from saathi.agent_runtime.test_authority import AUTHORITY_ENV, TEST_APPROVAL_STRATEGY


@pytest.fixture()
def store(tmp_path):
    return RunStore(db_path=tmp_path / "approval.db")


@pytest.fixture()
def orch(store):
    return Orchestrator(store=store, memory=False)


def _pending_run(monkeypatch, store, orch, *, objective="publish", conversation_id=""):
    """A run genuinely held at the orchestrator's approval gate."""
    from saathi.agent_runtime.service import start_agent_run

    monkeypatch.setenv(AUTHORITY_ENV, "1")
    rec = start_agent_run(objective=objective, strategy=TEST_APPROVAL_STRATEGY,
                          actor="user:test", conversation_id=conversation_id,
                          orchestrator=orch, execute=True)
    assert rec.ok
    rid = rec.run_id
    assert store.get_run(rid)["state"] == RunState.AWAITING_APPROVAL.value
    return rid, store.pending_approvals(rid)[0]["id"]


# ── approve / deny semantics ───────────────────────────────────────────────

def test_approve_resolves_the_approval_and_resumes_the_run(monkeypatch, store, orch):
    rid, aid = _pending_run(monkeypatch, store, orch)
    res = orch.approve(rid, aid, approved=True, actor="user:owner")

    assert res["status"] == "approved"
    assert res["resolved_by"] == "user:owner"
    assert res["resolved_at"]
    assert store.pending_approvals(rid) == []
    # Canonical: approved -> APPROVED -> RUNNING. The run may continue; nothing
    # here says it executed anything.
    assert store.get_run(rid)["state"] == RunState.RUNNING.value


def test_deny_fails_the_task_and_never_executes_it(monkeypatch, store, orch):
    rid, aid = _pending_run(monkeypatch, store, orch)
    res = orch.approve(rid, aid, approved=False, actor="user:owner")

    assert res["status"] == "denied"
    assert store.pending_approvals(rid) == []
    tasks = store.list_tasks(rid)
    assert all(t["status"] == "failed" for t in tasks), "denial must not execute"
    assert store.artifacts(rid) == [], "denial produces no work product"


def test_approval_is_not_execution_or_verification(monkeypatch, store, orch):
    rid, aid = _pending_run(monkeypatch, store, orch)
    orch.approve(rid, aid, approved=True, actor="user:owner")
    # Granting an approval asserts nothing about verification, and the run's own
    # later gates remain whatever they were.
    assert store.verifications(rid) == []


# ── replay and conflict ────────────────────────────────────────────────────

def test_replayed_approve_is_idempotent(monkeypatch, store, orch):
    rid, aid = _pending_run(monkeypatch, store, orch)
    first = orch.approve(rid, aid, approved=True, actor="user:owner")
    again = orch.approve(rid, aid, approved=True, actor="user:owner")
    assert again["status"] == first["status"] == "approved"
    assert again["resolved_at"] == first["resolved_at"], "not re-stamped"


def test_replayed_deny_is_idempotent(monkeypatch, store, orch):
    rid, aid = _pending_run(monkeypatch, store, orch)
    first = orch.approve(rid, aid, approved=False, actor="user:owner")
    again = orch.approve(rid, aid, approved=False, actor="user:owner")
    assert again["status"] == first["status"] == "denied"


def test_a_resolved_approval_cannot_be_flipped(monkeypatch, store, orch):
    rid, aid = _pending_run(monkeypatch, store, orch)
    orch.approve(rid, aid, approved=True, actor="user:owner")
    flipped = orch.approve(rid, aid, approved=False, actor="user:someone-else")
    assert flipped["status"] == "approved", "an approval is decided once"

    rid2, aid2 = _pending_run(monkeypatch, store, orch, objective="second")
    orch.approve(rid2, aid2, approved=False, actor="user:owner")
    flipped2 = orch.approve(rid2, aid2, approved=True, actor="user:owner")
    assert flipped2["status"] == "denied"


def test_concurrent_resolution_leaves_one_deterministic_outcome(monkeypatch, store, orch):
    rid, aid = _pending_run(monkeypatch, store, orch)
    outcomes = [orch.approve(rid, aid, approved=(i % 2 == 0), actor=f"user:{i}")["status"]
                for i in range(6)]
    # Whatever landed first wins for every subsequent caller.
    assert len(set(outcomes)) == 1
    assert store.get_approval(aid)["status"] == outcomes[0]


# ── expiry ─────────────────────────────────────────────────────────────────

def test_an_expired_approval_resolves_as_expired_not_approved(store):
    rid = store.create_run(objective="x", strategy="c", actor="u")
    aid = store.add_approval(rid, agent="executor", action="send", risk=3, ttl_sec=-1)
    res = store.resolve_approval(aid, approved=True, actor="user:owner")
    assert res["status"] == "expired", "expiry outranks the caller's intent"


def test_expiry_is_backend_time_not_the_callers(store):
    rid = store.create_run(objective="x", strategy="c", actor="u")
    live = store.add_approval(rid, agent="executor", action="send", risk=3, ttl_sec=3600)
    assert store.get_approval(live)["expires_at"] > store.get_approval(live)["created_at"]
    assert store.resolve_approval(live, approved=True, actor="u")["status"] == "approved"


# ── audit evidence ─────────────────────────────────────────────────────────

def test_resolution_leaves_durable_audit_evidence(monkeypatch, store, orch):
    rid, aid = _pending_run(monkeypatch, store, orch)
    orch.approve(rid, aid, approved=True, actor="user:owner")

    resolved = [e for e in store.events(rid) if e["name"] == "approval.resolved"]
    assert len(resolved) == 1
    payload = resolved[0]["payload"]
    assert payload["id"] == aid
    assert payload["status"] == "approved"
    assert payload["actor"] == "user:owner"

    # And on the record itself, so evidence does not depend on the event stream.
    rec = store.get_approval(aid)
    assert rec["resolved_by"] == "user:owner" and rec["resolved_at"]


def test_audit_carries_no_session_material(monkeypatch, store, orch):
    rid, aid = _pending_run(monkeypatch, store, orch)
    orch.approve(rid, aid, approved=True, actor="user:owner")
    blob = str(store.events(rid)) + str(store.get_approval(aid))
    for secret in ("token", "session", "password", "cookie", "authorization"):
        assert secret not in blob.lower(), f"{secret} must not reach audit"


# ── the HTTP route: binding, errors, CSRF ──────────────────────────────────

@pytest.fixture()
def client(monkeypatch, store, orch):
    """The real app with auth bypassed, so route logic is what is under test."""
    import saathi.agent_runtime.api as api
    import saathi.server as server

    monkeypatch.setattr(api, "default_orchestrator", lambda: orch)
    monkeypatch.setattr(server, "_is_authed", lambda request: True)
    return TestClient(server.app)


def test_an_approval_must_belong_to_the_run_in_the_url(monkeypatch, store, orch, client):
    """The defect this route was shipped with.

    Resolving by approval id alone let one run's id carry another run's approval:
    the wrong approval was resolved, and the run named in the URL was moved out
    of AWAITING_APPROVAL without its own approval ever being decided.
    """
    rid_a, aid_a = _pending_run(monkeypatch, store, orch, objective="run a")
    rid_b, aid_b = _pending_run(monkeypatch, store, orch, objective="run b")

    r = client.post(f"/api/v1/agents/runs/{rid_a}/approve",
                    json={"approval_id": aid_b, "approved": True})
    assert r.status_code == 404
    assert r.json()["error"] == "APPROVAL_NOT_FOUND"

    # Neither run moved, and neither approval was decided.
    for rid, aid in ((rid_a, aid_a), (rid_b, aid_b)):
        assert store.get_run(rid)["state"] == RunState.AWAITING_APPROVAL.value
        assert store.get_approval(aid)["status"] == "pending"


def test_an_unknown_approval_is_not_found_rather_than_a_crash(monkeypatch, store, orch, client):
    rid, _ = _pending_run(monkeypatch, store, orch)
    r = client.post(f"/api/v1/agents/runs/{rid}/approve",
                    json={"approval_id": "does-not-exist", "approved": True})
    assert r.status_code == 404


def test_a_cross_site_origin_is_refused(monkeypatch, store, orch, client):
    """The session cookie is SameSite=None, so another origin could otherwise
    drive this mutation with the user's own cookie."""
    rid, aid = _pending_run(monkeypatch, store, orch)
    r = client.post(f"/api/v1/agents/runs/{rid}/approve",
                    json={"approval_id": aid, "approved": True},
                    headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
    assert r.json()["error"] == "ORIGIN_REJECTED"
    assert store.get_approval(aid)["status"] == "pending", "nothing was decided"


def test_an_allowed_origin_still_works(monkeypatch, store, orch, client):
    rid, aid = _pending_run(monkeypatch, store, orch)
    r = client.post(f"/api/v1/agents/runs/{rid}/approve",
                    json={"approval_id": aid, "approved": True},
                    headers={"Origin": "http://127.0.0.1:3000"})
    assert r.status_code == 200 and r.json()["status"] == "approved"


def test_a_request_without_an_origin_is_unaffected(monkeypatch, store, orch, client):
    # Not a browser CSRF vector; server-to-server callers must keep working.
    rid, aid = _pending_run(monkeypatch, store, orch)
    r = client.post(f"/api/v1/agents/runs/{rid}/approve",
                    json={"approval_id": aid, "approved": True})
    assert r.status_code == 200


def test_unauthenticated_mutation_is_rejected(store, orch, monkeypatch):
    import saathi.agent_runtime.api as api
    import saathi.server as server

    monkeypatch.setattr(api, "default_orchestrator", lambda: orch)
    rid, aid = _pending_run(monkeypatch, store, orch)
    with TestClient(server.app) as c:
        r = c.post(f"/api/v1/agents/runs/{rid}/approve",
                   json={"approval_id": aid, "approved": True})
    assert r.status_code == 401
    assert store.get_approval(aid)["status"] == "pending"


# ── the boundaries this phase must not cross ───────────────────────────────

def test_no_guardian_or_gateway_control_was_added():
    import saathi.agent_runtime.api as api

    routes = {r.path for r in api.router.routes}
    for forbidden in ("/api/v1/agents/runs/{rid}/unblock",
                      "/api/v1/agents/runs/{rid}/recover",
                      "/api/v1/agents/runs/{rid}/execute-now",
                      "/api/v1/agents/runs/{rid}/override"):
        assert forbidden not in routes


def test_approval_fixture_gating_is_unchanged():
    from saathi.agent_runtime.test_authority import strategy_allowed
    for name in ("build", "document", "business", "broad_research"):
        assert "executor" not in strategies.STRATEGIES[name]
        assert strategy_allowed(name) is True


def test_a_denied_run_does_not_strand_in_awaiting_approval(monkeypatch, store, orch):
    """Regression: denial left the run unresolvable.

    The denial branch attempted AWAITING_APPROVAL -> RUNNING, which the state
    machine does not allow, so the transition was silently swallowed and the run
    sat in AWAITING_APPROVAL with zero pending approvals -- an authority row no
    one could act on and nothing could clear. Found by exercising denial in the
    browser during Phase 11.
    """
    rid, aid = _pending_run(monkeypatch, store, orch)
    orch.approve(rid, aid, approved=False, actor="user:owner")

    state = store.get_run(rid)["state"]
    assert state != RunState.AWAITING_APPROVAL.value, "a refused run must not stay held"
    assert state == RunState.CANCELLED.value
    assert store.pending_approvals(rid) == []


def test_a_denied_run_leaves_authority_entirely(monkeypatch, store, orch):
    rid, aid = _pending_run(monkeypatch, store, orch)
    orch.approve(rid, aid, approved=False, actor="user:owner")
    # Neither of the two authority states, so the Authority Centre stops showing it.
    assert store.get_run(rid)["state"] not in (
        RunState.AWAITING_APPROVAL.value, RunState.BLOCKED.value)
    assert store.authority_runs(limit=50) == [] or rid not in [
        r["id"] for r in store.authority_runs(limit=50)]
