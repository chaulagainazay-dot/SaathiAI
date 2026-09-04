"""Phase 13 — authority on every run-control mutation.

Phase 12 secured `approve`. Pause, resume, cancel, retry and execute mutated run
state through the same router with no actor, no permission check and no audit.

Four layers, none substituting for another: authentication identifies a session,
identity names the actor, RBAC decides whether they may ask, and the lifecycle
decides whether the transition is legal.
"""
import pytest
from fastapi.testclient import TestClient

from saathi.agent_runtime.api import FUTURE_PERMISSIONS
from saathi.agent_runtime.models import RunState
from saathi.agent_runtime.orchestrator import Orchestrator
from saathi.agent_runtime.store import RunStore
from saathi.security.store import SecurityStore

MUTATIONS = ("pause", "resume", "cancel", "execute")


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


def _run(store, orch, *, state=RunState.RUNNING, objective="work"):
    rid = store.create_run(objective=objective, strategy="build", actor="u")
    store.transition(rid, RunState.PLANNING)
    orch._build_tasks(rid, objective, "build", "")
    store.transition(rid, RunState.QUEUED)
    if state is not RunState.QUEUED:
        store.transition(rid, RunState.RUNNING)
    return rid


def _owner(sec, client):
    client.headers.update({"x-baadar-session": _session(sec, "role-owner")})


def _viewer(sec, client):
    client.headers.update({"x-baadar-session": _session(sec, "role-viewer")})


# ── every route requires authentication ────────────────────────────────────

@pytest.mark.parametrize("action", MUTATIONS)
def test_unauthenticated_mutation_is_rejected(monkeypatch, sec, store, orch, action):
    import saathi.agent_runtime.api as api
    import saathi.server as server

    monkeypatch.setattr(api, "default_orchestrator", lambda: orch)
    rid = _run(store, orch)
    before = store.get_run(rid)["state"]
    with TestClient(server.app) as c:
        r = c.post(f"/api/v1/agents/runs/{rid}/{action}")
    assert r.status_code == 401
    assert store.get_run(rid)["state"] == before, "nothing may change"


def test_unauthenticated_retry_is_rejected(monkeypatch, sec, store, orch):
    import saathi.agent_runtime.api as api
    import saathi.server as server

    monkeypatch.setattr(api, "default_orchestrator", lambda: orch)
    rid = _run(store, orch)
    tid = store.list_tasks(rid)[0]["id"]
    with TestClient(server.app) as c:
        r = c.post(f"/api/v1/agents/runs/{rid}/tasks/{tid}/retry")
    assert r.status_code == 401


# ── every route requires authorisation ─────────────────────────────────────

@pytest.mark.parametrize("action", MUTATIONS)
def test_a_viewer_cannot_control_a_run(sec, store, orch, client, action):
    rid = _run(store, orch)
    before = store.get_run(rid)["state"]
    _viewer(sec, client)

    r = client.post(f"/api/v1/agents/runs/{rid}/{action}")
    assert r.status_code == 403
    assert r.json()["error"] == "NOT_AUTHORIZED"
    assert store.get_run(rid)["state"] == before, f"{action} must not have happened"


def test_a_viewer_cannot_retry_a_task(sec, store, orch, client):
    rid = _run(store, orch)
    tid = store.list_tasks(rid)[0]["id"]
    store.update_task(tid, status="failed")
    _viewer(sec, client)

    r = client.post(f"/api/v1/agents/runs/{rid}/tasks/{tid}/retry")
    assert r.status_code == 403
    assert store.list_tasks(rid)[0]["status"] == "failed", "the task must not be reset"


def test_a_user_with_no_role_controls_nothing(sec, store, orch, client):
    from saathi import sessions

    rid = _run(store, orch)
    uid = sec.owner_id()
    with sec.db as db:
        db.execute("DELETE FROM user_roles WHERE user_id=?", (uid,))
    client.headers.update({"x-baadar-session": sessions.create(ua="t", ip="127.0.0.1")})

    assert client.post(f"/api/v1/agents/runs/{rid}/pause").status_code == 403


def test_an_authenticated_caller_without_a_session_is_refused(sec, store, orch, client):
    # `_is_authed` is patched True: authentication passes, but there is no one
    # to authorise, and the request is refused rather than treated as the owner.
    rid = _run(store, orch)
    r = client.post(f"/api/v1/agents/runs/{rid}/pause")
    assert r.status_code == 403


# ── 403 before existence disclosure ────────────────────────────────────────

@pytest.mark.parametrize("action", MUTATIONS)
def test_an_unauthorized_caller_cannot_probe_run_existence(sec, store, orch, client, action):
    real = _run(store, orch)
    _viewer(sec, client)

    a = client.post(f"/api/v1/agents/runs/{real}/{action}")
    b = client.post(f"/api/v1/agents/runs/does-not-exist/{action}")
    assert a.status_code == b.status_code == 403, "real and fake ids answer alike"
    assert a.json() == b.json()


def test_an_unauthorized_caller_cannot_probe_task_existence(sec, store, orch, client):
    rid = _run(store, orch)
    tid = store.list_tasks(rid)[0]["id"]
    _viewer(sec, client)

    a = client.post(f"/api/v1/agents/runs/{rid}/tasks/{tid}/retry")
    b = client.post(f"/api/v1/agents/runs/{rid}/tasks/nope/retry")
    assert a.status_code == b.status_code == 403
    assert a.json() == b.json()


def test_an_authorized_caller_does_get_a_real_answer(sec, store, orch, client):
    _owner(sec, client)
    r = client.post("/api/v1/agents/runs/does-not-exist/pause")
    assert r.status_code == 404, "authorised callers learn the truth"
    assert r.json()["error"] == "RUN_NOT_FOUND"


# ── resource binding: retry must not cross runs ────────────────────────────

def test_a_task_cannot_be_retried_through_another_runs_url(sec, store, orch, client):
    """The defect this milestone found.

    `retry_task` resets a task by id, so a request addressed to run A reset a
    task owned by run B and then ran A -- reproduced against the real store
    before the binding check existed.
    """
    a = _run(store, orch, objective="run a")
    b = _run(store, orch, objective="run b")
    task_b = store.list_tasks(b)[0]["id"]
    store.update_task(task_b, status="failed")
    _owner(sec, client)

    r = client.post(f"/api/v1/agents/runs/{a}/tasks/{task_b}/retry")
    assert r.status_code == 404
    assert r.json()["error"] == "TASK_NOT_FOUND"
    assert store.list_tasks(b)[0]["status"] == "failed", "run B was not touched"


def test_the_orchestrator_refuses_a_cross_run_retry_directly(store, orch):
    # Defence in depth: a caller that bypasses the route must also be refused.
    a = _run(store, orch, objective="a")
    b = _run(store, orch, objective="b")
    task_b = store.list_tasks(b)[0]["id"]
    store.update_task(task_b, status="failed")

    out = orch.retry_task(a, task_b)
    assert out.get("note") == "task_not_in_run"
    assert store.list_tasks(b)[0]["status"] == "failed"


def test_an_unknown_task_on_a_real_run_is_not_found(sec, store, orch, client):
    rid = _run(store, orch)
    _owner(sec, client)
    r = client.post(f"/api/v1/agents/runs/{rid}/tasks/no-such-task/retry")
    assert r.status_code == 404


# ── lifecycle legality is independent of RBAC ──────────────────────────────

def test_permission_does_not_make_an_illegal_transition_legal(sec, store, orch, client):
    """Being authorised is not being able. A completed run cannot be resumed."""
    rid = _run(store, orch)
    store.transition(rid, RunState.COMPLETED)
    _owner(sec, client)

    r = client.post(f"/api/v1/agents/runs/{rid}/resume")
    assert r.status_code == 409, "a state conflict, not a server fault"
    assert store.get_run(rid)["state"] == RunState.COMPLETED.value


def test_pause_reports_what_the_lifecycle_actually_did(sec, store, orch, client):
    """Previously this claimed paused=True unconditionally."""
    rid = _run(store, orch)
    store.transition(rid, RunState.COMPLETED)
    _owner(sec, client)

    r = client.post(f"/api/v1/agents/runs/{rid}/pause")
    assert r.status_code == 200
    assert r.json()["paused"] is False, "a terminal run did not pause"
    assert r.json()["state"] == RunState.COMPLETED.value


def test_a_valid_pause_is_reported_truthfully(sec, store, orch, client):
    rid = _run(store, orch)
    _owner(sec, client)

    r = client.post(f"/api/v1/agents/runs/{rid}/pause")
    assert r.status_code == 200 and r.json()["paused"] is True
    assert store.get_run(rid)["state"] == RunState.PAUSED.value


# ── the approval boundary must hold ────────────────────────────────────────

def test_resume_cannot_release_a_run_held_for_approval(sec, store, orch, client):
    """Critical: general run-control permission is not approval authority.

    AWAITING_APPROVAL has no legal edge to RUNNING, so a `write` holder cannot
    use resume to walk a run past its approval gate.
    """
    rid = _run(store, orch)
    store.transition(rid, RunState.AWAITING_APPROVAL)
    _owner(sec, client)

    r = client.post(f"/api/v1/agents/runs/{rid}/resume")
    assert r.status_code == 409
    assert store.get_run(rid)["state"] == RunState.AWAITING_APPROVAL.value, \
        "the run is still held for approval"


def test_retry_cannot_release_a_run_held_for_approval(sec, store, orch, client):
    rid = _run(store, orch)
    tid = store.list_tasks(rid)[0]["id"]
    store.transition(rid, RunState.AWAITING_APPROVAL)
    _owner(sec, client)

    client.post(f"/api/v1/agents/runs/{rid}/tasks/{tid}/retry")
    assert store.get_run(rid)["state"] != RunState.RUNNING.value, \
        "retry must not walk a held run into RUNNING"


def test_run_control_creates_no_approval(sec, store, orch, client):
    rid = _run(store, orch)
    _owner(sec, client)
    for action in ("pause", "resume", "cancel"):
        client.post(f"/api/v1/agents/runs/{rid}/{action}")
    assert store.pending_approvals(rid) == [], "no run control may mint an approval"


# ── replay ─────────────────────────────────────────────────────────────────

def test_repeated_cancel_is_safe(sec, store, orch, client):
    rid = _run(store, orch)
    _owner(sec, client)

    first = client.post(f"/api/v1/agents/runs/{rid}/cancel")
    state_after_first = store.get_run(rid)["state"]
    second = client.post(f"/api/v1/agents/runs/{rid}/cancel")

    assert first.status_code == second.status_code == 200
    assert store.get_run(rid)["state"] == state_after_first, "no second transition"


def test_repeated_pause_is_safe(sec, store, orch, client):
    rid = _run(store, orch)
    _owner(sec, client)

    client.post(f"/api/v1/agents/runs/{rid}/pause")
    assert store.get_run(rid)["state"] == RunState.PAUSED.value
    r = client.post(f"/api/v1/agents/runs/{rid}/pause")
    assert r.status_code == 200
    assert store.get_run(rid)["state"] == RunState.PAUSED.value


def test_cancel_then_resume_does_not_revive(sec, store, orch, client):
    rid = _run(store, orch)
    _owner(sec, client)
    client.post(f"/api/v1/agents/runs/{rid}/cancel")
    cancelled = store.get_run(rid)["state"]

    client.post(f"/api/v1/agents/runs/{rid}/resume")
    assert store.get_run(rid)["state"] == cancelled, "a cancelled run stays cancelled"


# ── audit ──────────────────────────────────────────────────────────────────

def test_a_successful_mutation_audits_the_real_actor(sec, store, orch, client):
    rid = _run(store, orch)
    uid = sec.owner_id()
    _owner(sec, client)

    client.post(f"/api/v1/agents/runs/{rid}/pause")

    rows = [e for e in sec.audit_recent(limit=20) if e["event"] == "run.pause"]
    assert rows, "an authority mutation must be audited"
    assert rows[0]["user_id"] == uid
    assert rid[:32] in (rows[0]["detail"] or ""), "the audit names the resource"
    assert "ajay" not in str(rows[0])


@pytest.mark.parametrize("action", ["pause", "resume", "cancel", "execute"])
def test_a_refused_mutation_is_audited(sec, store, orch, client, action):
    rid = _run(store, orch)
    _viewer(sec, client)

    client.post(f"/api/v1/agents/runs/{rid}/{action}")

    denied = [e for e in sec.audit_recent(limit=30)
              if e["event"] == f"run.{action}.denied_unauthorized"]
    assert denied, f"a refused {action} is exactly what audit is for"
    assert denied[0]["ok"] == 0


def test_a_refused_retry_is_audited(sec, store, orch, client):
    rid = _run(store, orch)
    tid = store.list_tasks(rid)[0]["id"]
    _viewer(sec, client)

    client.post(f"/api/v1/agents/runs/{rid}/tasks/{tid}/retry")
    denied = [e for e in sec.audit_recent(limit=30)
              if e["event"] == "task.retry.denied_unauthorized"]
    assert denied and denied[0]["ok"] == 0


def test_audit_never_records_the_session_token(sec, store, orch, client):
    rid = _run(store, orch)
    token = _session(sec, "role-owner")
    client.headers.update({"x-baadar-session": token})

    for action in ("pause", "resume", "cancel"):
        client.post(f"/api/v1/agents/runs/{rid}/{action}")

    blob = str(sec.audit_recent(limit=40))
    assert token not in blob, "the credential that authenticated the call must not be logged"
    for secret in ("password", "cookie", "bootstrap"):
        assert secret not in blob.lower()
    # "authorization" is checked in its credential-bearing forms only. The bare
    # word is legitimate vocabulary in this log -- Phase 16 writes the machine-safe
    # status code `authorization.granted` -- and a substring match on it flags a
    # correct audit entry while catching no actual secret. What must never appear
    # is a header or assignment that would carry a value.
    lowered = blob.lower()
    for form in ("authorization:", "authorization=", "authorization\":",
                 "bearer ", "x-baadar-session"):
        assert form not in lowered, form


def test_audit_action_names_are_stable_identifiers(sec, store, orch, client):
    rid = _run(store, orch)
    _owner(sec, client)
    for action in ("pause", "cancel"):
        client.post(f"/api/v1/agents/runs/{rid}/{action}")

    events = {e["event"] for e in sec.audit_recent(limit=20)}
    assert {"run.pause", "run.cancel"} <= events, "machine-safe keys, not prose"
    for e in events:
        assert " " not in e


# ── the boundaries this milestone must not cross ───────────────────────────

def test_no_execution_readiness_concept_was_introduced():
    import saathi.agent_runtime.api as api

    src = open(api.__file__).read()
    for banned in ("EXECUTION_ALLOWED", "EXECUTION_READY", "SAFE_TO_EXECUTE",
                   "APPROVED_FOR_EXECUTION"):
        assert banned not in src, f"{banned} is a later milestone"


def test_no_guardian_or_gateway_control_was_added():
    import saathi.agent_runtime.api as api

    routes = {r.path for r in api.router.routes}
    for forbidden in ("/api/v1/agents/runs/{rid}/unblock",
                      "/api/v1/agents/runs/{rid}/recover",
                      "/api/v1/agents/runs/{rid}/override",
                      "/api/v1/agents/guardian",
                      "/api/v1/agents/kill-switch"):
        assert forbidden not in routes


def test_run_control_touches_no_financial_authority(sec, store, orch, client):
    """Control may cause work; it may never cause *authority*.

    Note `resume` is not a passive control: it transitions to RUNNING and
    re-enters execution, so agents legitimately run and record verifications.
    What must never appear is a tool request -- the external-side-effect path --
    or an approval, because neither is control's to create.
    """
    rid = _run(store, orch)
    _owner(sec, client)
    for action in ("pause", "resume", "cancel"):
        client.post(f"/api/v1/agents/runs/{rid}/{action}")

    assert store.tool_requests(rid) == [], "control must not request a tool"
    assert store.pending_approvals(rid) == [], "control must not mint an approval"


def test_the_coarse_permission_mapping_is_documented():
    """The temporary mapping must stay visible rather than becoming silent debt."""
    assert set(FUTURE_PERMISSIONS) >= {
        "approval.resolve", "run.pause", "run.resume",
        "run.cancel", "run.execute", "task.retry"}
    for name, description in FUTURE_PERMISSIONS.items():
        assert "." in name and description
