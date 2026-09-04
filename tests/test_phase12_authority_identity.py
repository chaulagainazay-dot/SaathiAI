"""Phase 12 — actor identity and RBAC on authority mutation.

Authentication answers "is this a live session". Authorisation answers "may this
user decide this". They were the same check, so any authenticated caller could
resolve any approval, and every resolution was audited as a hardcoded name.
"""
import pytest
from fastapi.testclient import TestClient

from saathi.agent_runtime.api import APPROVAL_PERMISSION
from saathi.agent_runtime.models import RunState
from saathi.agent_runtime.orchestrator import Orchestrator
from saathi.agent_runtime.store import RunStore
from saathi.agent_runtime.test_authority import AUTHORITY_ENV, TEST_APPROVAL_STRATEGY
from saathi.security.store import SecurityStore


@pytest.fixture()
def sec(tmp_path):
    """A properly bootstrapped store.

    D14 refuses to create an owner without a bootstrap marker -- correctly -- so
    the repository's own helper performs the same transition the real bootstrap
    does rather than bypassing it.
    """
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


def _pending_run(monkeypatch, store, orch, *, objective="publish"):
    from saathi.agent_runtime.service import start_agent_run

    monkeypatch.setenv(AUTHORITY_ENV, "1")
    rec = start_agent_run(objective=objective, strategy=TEST_APPROVAL_STRATEGY,
                          actor="user:test", orchestrator=orch, execute=True)
    assert rec.ok
    return rec.run_id, store.pending_approvals(rec.run_id)[0]["id"]


# ── identity ───────────────────────────────────────────────────────────────

def test_a_live_session_names_its_user(sec, monkeypatch):
    from saathi import sessions

    monkeypatch.setattr(sessions, "_store", lambda: sec)
    uid = sec.owner_id()
    token = sessions.create(ua="test", ip="127.0.0.1")

    assert sessions.identify(token) == uid, "the id was always stored; now it is readable"


def test_an_unknown_or_dead_session_names_nobody(sec, monkeypatch):
    from saathi import sessions

    monkeypatch.setattr(sessions, "_store", lambda: sec)
    sec.get_or_create_owner()

    assert sessions.identify("") is None
    assert sessions.identify("not-a-real-token") is None

    token = sessions.create(ua="t", ip="127.0.0.1")
    sec.session_revoke(sessions.session_id(token))
    assert sessions.identify(token) is None, "a revoked session identifies nobody"


def test_identify_agrees_with_validate(sec, monkeypatch):
    from saathi import sessions

    monkeypatch.setattr(sessions, "_store", lambda: sec)
    sec.get_or_create_owner()
    token = sessions.create(ua="t", ip="127.0.0.1")
    # The two must never disagree: a session that authenticates must identify.
    assert sessions.validate(token) is True
    assert sessions.identify(token) is not None


# ── permissions ────────────────────────────────────────────────────────────

def test_the_owner_holds_everything(sec):
    uid = sec.owner_id()
    assert "*" in sec.permissions_for(uid)
    assert sec.has_permission(uid, APPROVAL_PERMISSION) is True
    assert sec.has_permission(uid, "anything-at-all") is True, "* is a wildcard"


def test_permissions_come_from_assigned_roles(sec):
    uid = sec.owner_id()
    with sec.db as db:
        db.execute("DELETE FROM user_roles WHERE user_id=?", (uid,))
        db.execute("INSERT INTO user_roles (user_id, role_id, assigned_at) VALUES (?,?,?)",
                   (uid, "role-viewer", 0))
    assert sec.permissions_for(uid) == {"read"}
    assert sec.has_permission(uid, "read") is True
    assert sec.has_permission(uid, APPROVAL_PERMISSION) is False, "a viewer cannot approve"


def test_permissions_union_across_several_roles(sec):
    uid = sec.owner_id()
    with sec.db as db:
        db.execute("DELETE FROM user_roles WHERE user_id=?", (uid,))
        for role in ("role-viewer", "role-member"):
            db.execute("INSERT INTO user_roles (user_id, role_id, assigned_at) VALUES (?,?,?)",
                       (uid, role, 0))
    assert {"read", "write"} <= sec.permissions_for(uid)
    assert sec.has_permission(uid, APPROVAL_PERMISSION) is True


def test_authorisation_fails_closed(sec):
    # Nobody, no roles, and no permission name all answer no.
    assert sec.permissions_for("") == set()
    assert sec.permissions_for("ghost-user") == set()
    assert sec.has_permission("", APPROVAL_PERMISSION) is False
    assert sec.has_permission("ghost-user", APPROVAL_PERMISSION) is False

    uid = sec.owner_id()
    assert sec.has_permission(uid, "") is False


def test_a_user_with_no_roles_is_authorised_for_nothing(sec):
    uid = sec.owner_id()
    with sec.db as db:
        db.execute("DELETE FROM user_roles WHERE user_id=?", (uid,))
    assert sec.permissions_for(uid) == set()
    assert sec.has_permission(uid, APPROVAL_PERMISSION) is False


# ── the route enforces it ──────────────────────────────────────────────────

@pytest.fixture()
def client(monkeypatch, sec, store, orch):
    """Real app, real route. Auth passes; authorisation is what is under test."""
    import saathi.agent_runtime.api as api
    import saathi.security.store as secstore
    import saathi.server as server
    from saathi import sessions

    monkeypatch.setattr(api, "default_orchestrator", lambda: orch)
    monkeypatch.setattr(server, "_is_authed", lambda request: True)
    monkeypatch.setattr(secstore, "get_store", lambda: sec)
    monkeypatch.setattr(sessions, "_store", lambda: sec)
    return TestClient(server.app)


def _session_for(sec, role_id: str) -> str:
    from saathi import sessions

    uid = sec.owner_id()
    with sec.db as db:
        db.execute("DELETE FROM user_roles WHERE user_id=?", (uid,))
        db.execute("INSERT INTO user_roles (user_id, role_id, assigned_at) VALUES (?,?,?)",
                   (uid, role_id, 0))
    return sessions.create(ua="test", ip="127.0.0.1")


def test_a_viewer_cannot_decide_an_approval(monkeypatch, sec, store, orch, client):
    rid, aid = _pending_run(monkeypatch, store, orch)
    token = _session_for(sec, "role-viewer")

    r = client.post(f"/api/v1/agents/runs/{rid}/approve",
                    json={"approval_id": aid, "approved": True},
                    headers={"x-baadar-session": token})
    assert r.status_code == 403
    assert r.json()["error"] == "NOT_AUTHORIZED"
    assert store.get_approval(aid)["status"] == "pending", "nothing was decided"
    assert store.get_run(rid)["state"] == RunState.AWAITING_APPROVAL.value


def test_an_owner_may_decide_an_approval(monkeypatch, sec, store, orch, client):
    rid, aid = _pending_run(monkeypatch, store, orch)
    token = _session_for(sec, "role-owner")

    r = client.post(f"/api/v1/agents/runs/{rid}/approve",
                    json={"approval_id": aid, "approved": True},
                    headers={"x-baadar-session": token})
    assert r.status_code == 200
    assert r.json()["status"] == "approved"


def test_an_authenticated_caller_without_a_session_is_refused(monkeypatch, sec, store, orch, client):
    """The gap this closes.

    `_is_authed` is patched True, so authentication succeeds. Without a session
    that names a user there is no one to authorise, and the request is refused
    rather than treated as the owner.
    """
    rid, aid = _pending_run(monkeypatch, store, orch)
    r = client.post(f"/api/v1/agents/runs/{rid}/approve",
                    json={"approval_id": aid, "approved": True})
    assert r.status_code == 403
    assert store.get_approval(aid)["status"] == "pending"


def test_authorisation_is_checked_before_the_approval_is_looked_up(
        monkeypatch, sec, store, orch, client):
    # An unauthorised caller must not learn whether an approval exists.
    rid, _ = _pending_run(monkeypatch, store, orch)
    token = _session_for(sec, "role-viewer")
    r = client.post(f"/api/v1/agents/runs/{rid}/approve",
                    json={"approval_id": "does-not-exist", "approved": True},
                    headers={"x-baadar-session": token})
    assert r.status_code == 403, "403 before 404, so nothing is disclosed"


# ── audit carries the real actor ───────────────────────────────────────────

def test_the_resolution_audits_the_real_user(monkeypatch, sec, store, orch, client):
    rid, aid = _pending_run(monkeypatch, store, orch)
    uid = sec.owner_id()
    token = _session_for(sec, "role-owner")

    client.post(f"/api/v1/agents/runs/{rid}/approve",
                json={"approval_id": aid, "approved": True},
                headers={"x-baadar-session": token})

    # The approval record names the actual caller, not a hardcoded name.
    assert store.get_approval(aid)["resolved_by"] == f"user:{uid}"
    assert "ajay" not in store.get_approval(aid)["resolved_by"]

    # And the security store holds a durable record of the decision.
    events = [e for e in sec.audit_recent(limit=20) if e["event"] == "approval.resolved"]
    assert events, "an authority decision must be audited"
    assert events[0]["user_id"] == uid
    assert events[0]["ok"] == 1


def test_a_refused_attempt_is_audited_too(monkeypatch, sec, store, orch, client):
    rid, aid = _pending_run(monkeypatch, store, orch)
    token = _session_for(sec, "role-viewer")

    client.post(f"/api/v1/agents/runs/{rid}/approve",
                json={"approval_id": aid, "approved": True},
                headers={"x-baadar-session": token})

    denied = [e for e in sec.audit_recent(limit=20)
              if e["event"] == "approval.denied_unauthorized"]
    assert denied, "a refused authority attempt is exactly what audit is for"
    assert denied[0]["ok"] == 0


def test_audit_never_records_the_session_token(monkeypatch, sec, store, orch, client):
    rid, aid = _pending_run(monkeypatch, store, orch)
    token = _session_for(sec, "role-owner")

    client.post(f"/api/v1/agents/runs/{rid}/approve",
                json={"approval_id": aid, "approved": True},
                headers={"x-baadar-session": token})

    blob = str(sec.audit_recent(limit=20))
    assert token not in blob, "the credential that authenticated the call must not be logged"
    for secret in ("password", "cookie", "authorization"):
        assert secret not in blob.lower()
