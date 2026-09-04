"""D15 — platform provisioning is bound to the canonical D14 owner.

D14 secured the canonical identity: an owner in the security store, created only
by a bootstrap demanding a one-time operator proof. It did not audit the
platform namespace, which kept a second identity system and its own way in.

``POST /api/v1/platform/bootstrap`` took no token, no session and no operator
proof. ``BootstrapBody`` defaulted every field, and an absent password selected a
"M50 compatibility: passwordless bootstrap" path. The auth middleware exempted
the entire ``/api/v1/platform/*`` prefix on the stated assumption that every
route under it enforces ``X-Platform-Token``; that one enforced nothing.

Proven during R2.1 validation: an empty ``{}`` POST from an unauthenticated
loopback caller returned 200 and created ``owner@local`` with an organisation,
workspace and owner membership. And because ``bootstrap_owner`` returns early
once any user exists, the first anonymous caller fixes the platform owner
permanently -- a legitimate operator can no longer claim it.

Every test here runs against stores created inside ``tmp_path``.
"""
from __future__ import annotations

import threading

import pytest
from fastapi.testclient import TestClient

SYNTHETIC_PASSWORD = "T3st!Platform#Pw"
LOOPBACK = ("127.0.0.1", 51234)


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """Fresh canonical + platform stores, wired to every singleton."""
    import sys, pathlib as _pl
    sys.path.insert(0, str(_pl.Path(__file__).resolve().parent))

    state = tmp_path / "state"
    state.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("SAATHI_STATE_ROOT", str(state))
    monkeypatch.setenv("SAATHI_LOAD_DOTENV", "false")
    monkeypatch.setenv("SAATHI_PLATFORM_DB", str(tmp_path / "platform.db"))
    for var in ("BAADAR_PASSWORD", "BAADAR_PASSWORD_HASH",
                "SAATHI_BOOTSTRAP_ENABLED", "SAATHI_BOOTSTRAP_TOKEN_FILE"):
        monkeypatch.delenv(var, raising=False)

    from saathi.security import store as store_mod
    from saathi.security.registry import close_registry
    from saathi.security.timeline import close_timeline
    from saathi.platform import service as platform_service

    store_mod.close_store()
    store_mod._default_store = None
    close_registry()
    close_timeline()
    sec = store_mod.SecurityStore(db_path=tmp_path / "security.db")
    store_mod._default_store = sec

    # The platform service is a process singleton too, and it caches its store.
    # Without this reset each test would inherit the previous test's platform
    # owner, which is precisely the state under test.
    platform_service.reset_platform_for_tests(tmp_path / "platform.db")

    import saathi.server as svr
    monkeypatch.setattr(svr, "_PASSWORD_HASH", "", raising=False)
    monkeypatch.setattr(svr, "ACCESS_TOKEN", "", raising=False)

    yield sec

    platform_service.reset_platform_for_tests(tmp_path / "platform-teardown.db")
    sec.close()
    store_mod.close_store()
    store_mod._default_store = None
    close_registry()
    close_timeline()


@pytest.fixture
def client():
    from saathi.server import app
    return TestClient(app, client=LOOPBACK)


def make_canonical_owner(store):
    """Put the canonical store into the state a real D14 bootstrap leaves."""
    from support.auth_state import make_active
    return make_active(store, password=SYNTHETIC_PASSWORD)


def owner_session(store):
    from saathi import sessions
    make_canonical_owner(store)
    return sessions.create(ua="pytest", ip="127.0.0.1", kind="password")


def platform_svc():
    from saathi.platform.service import default_platform
    return default_platform()


# ── the hole itself ─────────────────────────────────────────────────────────

def test_01_anonymous_empty_body_bootstrap_denied(client):
    """The exact request that created an owner during validation."""
    r = client.post("/api/v1/platform/bootstrap", json={})
    assert r.status_code in (401, 403), r.status_code
    assert platform_svc().store.list_users() == []


def test_02_anonymous_populated_body_bootstrap_denied(client):
    r = client.post("/api/v1/platform/bootstrap", json={
        "email": "attacker@example.com", "name": "Attacker",
        "org_name": "Attacker Org", "workspace_name": "Attacker WS",
        "password": "Attacker!Pass#123",
    })
    assert r.status_code in (401, 403)
    assert platform_svc().store.list_users() == []


def test_03_no_request_body_at_all_denied(client):
    r = client.post("/api/v1/platform/bootstrap")
    assert r.status_code in (401, 403, 422)
    assert platform_svc().store.list_users() == []


def test_04_loopback_alone_is_not_authorisation(client, isolated):
    """A loopback peer with no canonical session provisions nothing."""
    make_canonical_owner(isolated)          # canonically ACTIVE, but no session
    r = client.post("/api/v1/platform/bootstrap", json={})
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "CANONICAL_SESSION_REQUIRED"
    assert platform_svc().store.list_users() == []


@pytest.mark.parametrize("header", ["X-Forwarded-For", "X-Real-IP", "Forwarded"])
def test_05_forwarding_header_confers_nothing(client, header):
    r = client.post("/api/v1/platform/bootstrap", json={},
                    headers={header: "127.0.0.1"})
    assert r.status_code in (401, 403)
    assert platform_svc().store.list_users() == []


def test_06_canonical_uninitialised_denied(client):
    """No canonical owner means no identity to derive one from."""
    r = client.post("/api/v1/platform/bootstrap", json={},
                    headers={"x-baadar-session": "made-up-token"})
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "CANONICAL_NOT_ACTIVE"


def test_07_canonical_contaminated_denied(client, isolated):
    import secrets, time
    isolated.db.execute(
        "INSERT INTO users (id, email, name, created_at, updated_at) VALUES (?,?,?,?,?)",
        (secrets.token_hex(16), None, "planted", time.time(), time.time()))
    isolated.db.commit()
    r = client.post("/api/v1/platform/bootstrap", json={},
                    headers={"x-baadar-session": "made-up-token"})
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "CANONICAL_NOT_ACTIVE"


def test_08_canonical_active_owner_accepted(client, isolated):
    token = owner_session(isolated)
    r = client.post("/api/v1/platform/bootstrap", json={},
                    headers={"x-baadar-session": token})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["provisioned"] is True
    assert body["token"]
    assert len(platform_svc().store.list_users()) == 1


def test_09_revoked_canonical_session_cannot_provision(client, isolated):
    from saathi import sessions
    token = owner_session(isolated)
    sessions.revoke(sessions.session_id(token))
    r = client.post("/api/v1/platform/bootstrap", json={},
                    headers={"x-baadar-session": token})
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "CANONICAL_SESSION_INVALID"
    assert platform_svc().store.list_users() == []


def test_10_caller_supplied_identity_is_ignored(client, isolated):
    """Nothing in the body may choose the owner, its address or its org."""
    token = owner_session(isolated)
    r = client.post("/api/v1/platform/bootstrap", headers={"x-baadar-session": token},
                    json={"email": "attacker@example.com", "name": "Attacker",
                          "org_name": "Attacker Org", "workspace_name": "Attacker WS",
                          "password": "Attacker!Pass#123"})
    assert r.status_code == 200, r.text
    user = r.json()["user"]
    assert user["email"] != "attacker@example.com"
    assert user["name"] != "Attacker"
    assert r.json()["org"]["name"] != "Attacker Org"

    # Not merely "different from what the attacker asked for" — it must be the
    # canonical owner's own identity, read from the security store. A hardcoded
    # default would also differ from the attacker's input while still ignoring
    # who the owner actually is.
    owner_id = isolated.owner_id()
    canonical = isolated.get_user(owner_id) or {}
    assert user["email"] == canonical.get("email")
    assert user["name"] == canonical.get("name")


def test_11_provisioning_is_idempotent(client, isolated):
    token = owner_session(isolated)
    first = client.post("/api/v1/platform/bootstrap", json={},
                        headers={"x-baadar-session": token})
    second = client.post("/api/v1/platform/bootstrap", json={},
                         headers={"x-baadar-session": token})
    assert first.status_code == second.status_code == 200
    assert first.json()["provisioned"] is True
    assert second.json()["provisioned"] is False
    assert first.json()["user"]["user_id"] == second.json()["user"]["user_id"]
    assert len(platform_svc().store.list_users()) == 1
    # A fresh session each time, never the same raw token reissued.
    assert first.json()["token"] != second.json()["token"]


def test_12_concurrent_provisioning_has_exactly_one_winner(client, isolated):
    token = owner_session(isolated)
    results: list[object] = []
    lock = threading.Lock()

    def attempt():
        r = client.post("/api/v1/platform/bootstrap", json={},
                        headers={"x-baadar-session": token})
        with lock:
            results.append((r.status_code, r.json().get("provisioned")))

    threads = [threading.Thread(target=attempt) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert all(code == 200 for code, _ in results), results
    assert sum(1 for _, created in results if created is True) == 1, results
    assert len(platform_svc().store.list_users()) == 1


def test_13_planted_platform_owner_is_refused_not_adopted(client, isolated):
    """The anonymous-bootstrap fingerprint fails closed and is preserved."""
    svc = platform_svc()
    svc.bootstrap_owner(email="owner@local", name="Owner")     # the planted shape
    before = [u.user_id for u in svc.store.list_users()]

    token = owner_session(isolated)
    r = client.post("/api/v1/platform/bootstrap", json={},
                    headers={"x-baadar-session": token})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "PLATFORM_STATE_CONTAMINATED"
    # Nothing deleted, nothing rewritten: the rows are the evidence.
    assert [u.user_id for u in svc.store.list_users()] == before


def test_14_derived_session_is_bound_to_the_canonical_principal(client, isolated):
    from saathi import sessions
    token = owner_session(isolated)
    r = client.post("/api/v1/platform/bootstrap", json={},
                    headers={"x-baadar-session": token})
    assert r.status_code == 200

    svc = platform_svc()
    sess = svc.store.session_by_token(r.json()["token"])
    assert sess is not None
    assert sessions.session_id(token)[:12] in (sess.label or "")

    canonical = isolated.session_by_hash(sessions._hash(token)) or {}
    # The exchanged credential may not outlive the authority it came from.
    assert sess.expires_at <= float(canonical["expires_at"]) + 1.0


def test_14b_derived_session_expiry_tracks_a_short_canonical_session(client, isolated):
    """A fixed TTL would pass the previous check and still be wrong.

    Canonical sessions are long-lived by default, so any ceiling under 24h looks
    correct. Shortening the canonical session is what distinguishes "bounded by
    the principal" from "bounded by a constant".
    """
    import time
    from saathi import sessions

    token = owner_session(isolated)
    short_expiry = time.time() + 120.0
    isolated.db.execute("UPDATE sessions SET expires_at=? WHERE token_hash=?",
                        (short_expiry, sessions._hash(token)))
    isolated.db.commit()

    r = client.post("/api/v1/platform/bootstrap", json={},
                    headers={"x-baadar-session": token})
    assert r.status_code == 200, r.text
    sess = platform_svc().store.session_by_token(r.json()["token"])
    assert sess.expires_at <= short_expiry + 1.0, (sess.expires_at, short_expiry)


def test_14c_derived_role_is_read_from_membership_not_hardcoded(client, isolated):
    """The session's role must come from the store, never from a literal."""
    import ast
    import inspect
    from saathi.platform import canonical_link

    tree = ast.parse(inspect.getsource(canonical_link))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr == "create_session":
            role = [k for k in node.keywords if k.arg == "role"]
            assert role, "create_session must pass an explicit role"
            assert not isinstance(role[0].value, ast.Constant), \
                "role must be derived from membership, not a hardcoded literal"
            break
    else:
        raise AssertionError("no create_session call found")


def test_15_no_platform_password_or_credential_is_written(client, isolated):
    token = owner_session(isolated)
    assert client.post("/api/v1/platform/bootstrap", json={},
                       headers={"x-baadar-session": token}).status_code == 200
    svc = platform_svc()
    rows = svc.store._conn.execute("SELECT COUNT(*) FROM credentials").fetchone()[0]
    assert rows == 0, "provisioning must not mint a second password"


def test_16_secure_and_passwordless_bootstrap_paths_are_unreachable_by_route():
    """Neither legacy provisioning path may be reachable from the HTTP route."""
    import ast
    import inspect
    from saathi.platform import api

    src = inspect.getsource(api.platform_bootstrap)
    tree = ast.parse(src.strip())
    body = ast.dump(tree)
    assert "bootstrap_owner_secure" not in body
    assert "'bootstrap_owner'" not in body and '"bootstrap_owner"' not in body
    assert "provision_for_request" in body


# ── the middleware allowlist ────────────────────────────────────────────────

def test_17_blanket_platform_prefix_exemption_cannot_return():
    import inspect
    import saathi.server as svr

    src = inspect.getsource(svr._auth)
    code = "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))
    assert 'path.startswith("/api/v1/platform/")' not in code or \
        "_presents_platform_credential" in code, \
        "the platform prefix may only be exempt when a credential is presented"
    assert "_PUBLIC_PLATFORM_PATHS" in code


def test_18_public_platform_endpoints_still_work(client):
    for path in ("/api/v1/platform/health", "/api/v1/platform/provenance"):
        assert client.get(path).status_code == 200, path


def test_19_platform_routes_need_a_credential_to_reach_their_handler(client):
    """Anonymous callers no longer reach handlers that forgot to ask."""
    r = client.get("/api/v1/platform/agent/callers")
    assert r.status_code == 401, r.status_code


def test_20_bogus_platform_token_reaches_the_handler_and_is_refused(client):
    r = client.get("/api/v1/platform/voice/runtime/health",
                   headers={"X-Platform-Token": "not-a-real-token"})
    assert r.status_code in (401, 403)


# ── voice runtime, and the authority boundary ───────────────────────────────

def test_21_voice_runtime_requires_authenticated_owner_state(client):
    for method, path in (("post", "/api/v1/platform/voice/runtime/sessions"),
                         ("get", "/api/v1/platform/voice/runtime/health")):
        r = getattr(client, method)(path, **({"json": {}} if method == "post" else {}))
        assert r.status_code in (401, 403), (path, r.status_code)


def test_22_voice_authority_remains_none():
    from saathi.platform.tg import LIVE_TRADING_AUTHORIZED
    assert LIVE_TRADING_AUTHORIZED is False


def test_23_execution_gateway_still_fails_closed():
    from saathi.tools.registry import execute_tool
    out = execute_tool("send_email", {"to": "a@b.c", "subject": "s", "body": "b"})
    assert out.get("blocked") or out.get("error")


def test_24_approval_reference_is_server_minted_only():
    from saathi.tool_runtime.compat import try_canonical_legacy_tool
    out = try_canonical_legacy_tool("send_email",
                                    {"to": "a@b.c", "subject": "s", "body": "b"})
    assert out is None or out.get("error") == "approval_required"


def test_25_financial_and_account_change_ops_remain_blocked():
    from saathi.connectors.gov.side_effects import (
        ACCOUNT_CHANGE_OPERATIONS, FINANCIAL_OPERATIONS,
    )
    assert "change_password" in ACCOUNT_CHANGE_OPERATIONS
    assert "transfer" in FINANCIAL_OPERATIONS


def test_26_provisioning_grants_no_execution_or_approval_authority(client, isolated):
    """The exchanged session is an identity, not a capability grant."""
    token = owner_session(isolated)
    r = client.post("/api/v1/platform/bootstrap", json={},
                    headers={"x-baadar-session": token})
    assert r.status_code == 200
    plat = r.json()["token"]
    out = client.post("/api/v1/connectors/execute", json={},
                      headers={"X-Platform-Token": plat})
    assert out.status_code in (401, 403, 404, 409, 422)


# ── 27-29: the other half of the chain ──────────────────────────────────────
#
# Closing the anonymous bootstrap alone was not enough. POST
# /api/v1/platform/auth/login ended with a "M50 passwordless path (existing
# users without credentials)" fallback, so any caller who supplied an existing
# user's email and nothing else received a full platform session. The two holes
# composed: create owner@local anonymously, then log in as it anonymously.

def test_27_passwordless_login_is_refused(client, isolated):
    """A credential-less platform user must be unreachable by login."""
    svc = platform_svc()
    svc.bootstrap_owner(email="owner@local", name="Owner")   # no credential
    r = client.post("/api/v1/platform/auth/login", json={"email": "owner@local"})
    assert r.status_code in (401, 403), r.text
    assert "token" not in r.json()


def test_28_derived_identity_cannot_be_logged_into_without_a_credential(client, isolated):
    """The provisioned identity has no password, and none can be guessed into."""
    token = owner_session(isolated)
    prov = client.post("/api/v1/platform/bootstrap", json={},
                       headers={"x-baadar-session": token})
    assert prov.status_code == 200
    email = prov.json()["user"]["email"]

    for body in ({"email": email},
                 {"email": email, "password": ""},
                 {"email": email, "password": "guess"}):
        r = client.post("/api/v1/platform/auth/login", json=body)
        assert r.status_code in (401, 403), (body, r.text)
        assert "token" not in r.json()


def test_29_login_route_has_no_passwordless_fallback():
    import ast
    import inspect
    from saathi.platform import api

    tree = ast.parse(inspect.getsource(api.platform_login).strip())
    calls = [n.func.attr for n in ast.walk(tree)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)]
    assert "authenticate_login" in calls
    assert "login" not in calls, "the passwordless service login must not be reachable"
