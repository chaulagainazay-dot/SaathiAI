"""D14 — secure first-owner bootstrap, and the authority it must not grant.

Three attack classes are under test, all proved reachable by the Stage C trace:

1. unauthenticated fresh-install password provisioning
   (``/api/v1/auth/change-password`` on the bypass list, and
   ``/api/v1/auth/login`` letting *any* password through when nothing was
   configured);
2. ``_is_authed`` falling through to ``_is_local`` with no password, which made
   every loopback caller the owner on every protected route;
3. durable credential planting -- an API token or passkey minted during that
   window kept authenticating afterwards, because the token registry is
   consulted before any freshness condition.

Every test runs against a store created inside ``tmp_path``. Nothing here reads
or writes the operator's real state, and no real bootstrap token is ever
generated -- the tokens below are disposable synthetic values.
"""
from __future__ import annotations

import os
import pathlib
import secrets
import threading

import pytest
from fastapi.testclient import TestClient

SYNTHETIC_PASSWORD = "T3st!Bootstrap#Pw"
LOOPBACK = ("127.0.0.1", 51234)


# ── isolation ───────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def isolated_store(tmp_path, monkeypatch):
    """A fresh, empty security store per test, wired to every singleton."""
    state_root = tmp_path / "state"
    state_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("SAATHI_STATE_ROOT", str(state_root))
    monkeypatch.setenv("SAATHI_LOAD_DOTENV", "false")
    monkeypatch.delenv("BAADAR_PASSWORD", raising=False)
    monkeypatch.delenv("BAADAR_PASSWORD_HASH", raising=False)
    monkeypatch.delenv("SAATHI_BOOTSTRAP_ENABLED", raising=False)
    monkeypatch.delenv("SAATHI_BOOTSTRAP_TOKEN_FILE", raising=False)

    from saathi import auth_bootstrap, authsec
    from saathi.security import store as store_mod
    from saathi.security.registry import close_registry
    from saathi.security.timeline import close_timeline

    store_mod.close_store()
    store_mod._default_store = None
    close_registry()
    close_timeline()

    fresh = store_mod.SecurityStore(db_path=tmp_path / "security.db")
    store_mod._default_store = fresh

    # The server module binds these at import; a stale value from another test
    # would otherwise decide this one's outcome.
    import saathi.server as svr
    monkeypatch.setattr(svr, "_PASSWORD_HASH", "", raising=False)
    monkeypatch.setattr(svr, "_RAW_PASSWORD", "", raising=False)
    monkeypatch.setattr(svr, "ACCESS_TOKEN", "", raising=False)

    authsec._WINDOWS.clear()
    auth_bootstrap.reset_rate_limit_for_tests()

    yield fresh

    fresh.close()
    store_mod.close_store()
    store_mod._default_store = None
    close_registry()
    close_timeline()


@pytest.fixture
def client():
    from saathi.server import app
    return TestClient(app, client=LOOPBACK)


def arm(monkeypatch, tmp_path, *, token: str | None = None, mode: int = 0o600) -> str:
    """Arm bootstrap with a disposable synthetic operator token."""
    token = token or secrets.token_urlsafe(32)
    path = tmp_path / "operator.token"
    path.write_text(token)
    os.chmod(path, mode)
    monkeypatch.setenv("SAATHI_BOOTSTRAP_ENABLED", "true")
    monkeypatch.setenv("SAATHI_BOOTSTRAP_TOKEN_FILE", str(path))
    return token


def boot_body(token: str) -> dict:
    return {"operator_token": token, "new_password": SYNTHETIC_PASSWORD}


# ── 1-2: bootstrap is off by default, empty DB is not enough ────────────────

def test_01_bootstrap_disabled_by_default(client, tmp_path, monkeypatch):
    r = client.post("/api/v1/auth/bootstrap", json=boot_body("anything"))
    assert r.status_code == 403
    assert r.json()["error"] == "BOOTSTRAP_DISABLED"


def test_02_empty_database_alone_is_insufficient(client, isolated_store):
    from saathi import auth_bootstrap
    assert isolated_store.credential_census()["users"] == 0
    assert auth_bootstrap.auth_state(isolated_store) is auth_bootstrap.AuthState.UNINITIALIZED
    r = client.post("/api/v1/auth/bootstrap", json=boot_body("x"))
    assert r.status_code == 403


# ── 3-4: transport preconditions ────────────────────────────────────────────

def test_03_non_loopback_caller_denied(tmp_path, monkeypatch):
    from saathi.server import app
    token = arm(monkeypatch, tmp_path)
    remote = TestClient(app, client=("203.0.113.9", 4444))
    r = remote.post("/api/v1/auth/bootstrap", json=boot_body(token))
    assert r.status_code == 403
    assert r.json()["error"] == "BOOTSTRAP_NOT_LOOPBACK"


@pytest.mark.parametrize("header", [
    "X-Forwarded-For", "X-Forwarded-Host", "Forwarded", "X-Real-IP",
    "X-Client-IP", "True-Client-IP",
])
def test_04_forwarding_identity_header_denied(client, tmp_path, monkeypatch, header):
    token = arm(monkeypatch, tmp_path)
    r = client.post("/api/v1/auth/bootstrap", json=boot_body(token),
                    headers={header: "203.0.113.9"})
    assert r.status_code == 403
    assert r.json()["error"] == "BOOTSTRAP_PROXIED_REQUEST"


# ── 5-9: operator proof ─────────────────────────────────────────────────────

def test_05_missing_operator_token_denied(client, tmp_path, monkeypatch):
    arm(monkeypatch, tmp_path)
    r = client.post("/api/v1/auth/bootstrap", json=boot_body(""))
    assert r.status_code == 403
    assert r.json()["error"] == "BOOTSTRAP_TOKEN_MISSING"


def test_06_wrong_operator_token_denied(client, tmp_path, monkeypatch):
    arm(monkeypatch, tmp_path)
    r = client.post("/api/v1/auth/bootstrap", json=boot_body(secrets.token_urlsafe(32)))
    assert r.status_code == 403
    assert r.json()["error"] == "BOOTSTRAP_TOKEN_INVALID"


def test_07_expired_operator_token_denied(client, tmp_path, monkeypatch):
    token = arm(monkeypatch, tmp_path)
    path = pathlib.Path(os.environ["SAATHI_BOOTSTRAP_TOKEN_FILE"])
    old = path.stat().st_mtime - 10_000
    os.utime(path, (old, old))
    r = client.post("/api/v1/auth/bootstrap", json=boot_body(token))
    assert r.json()["error"] == "BOOTSTRAP_TOKEN_EXPIRED"


def test_08_insecure_token_file_mode_denied(client, tmp_path, monkeypatch):
    token = arm(monkeypatch, tmp_path, mode=0o644)
    r = client.post("/api/v1/auth/bootstrap", json=boot_body(token))
    assert r.json()["error"] == "BOOTSTRAP_TOKEN_FILE_INSECURE_MODE"


def test_09_symlinked_token_file_denied(client, tmp_path, monkeypatch):
    token = arm(monkeypatch, tmp_path)
    real = pathlib.Path(os.environ["SAATHI_BOOTSTRAP_TOKEN_FILE"])
    link = tmp_path / "linked.token"
    link.symlink_to(real)
    monkeypatch.setenv("SAATHI_BOOTSTRAP_TOKEN_FILE", str(link))
    r = client.post("/api/v1/auth/bootstrap", json=boot_body(token))
    assert r.json()["error"] == "BOOTSTRAP_TOKEN_FILE_UNREADABLE"


def test_09b_weak_token_denied(client, tmp_path, monkeypatch):
    token = arm(monkeypatch, tmp_path, token="short")
    r = client.post("/api/v1/auth/bootstrap", json=boot_body(token))
    assert r.json()["error"] == "BOOTSTRAP_TOKEN_TOO_WEAK"


# ── 10-18: the happy path and its guarantees ────────────────────────────────

def test_10_armed_loopback_bootstrap_succeeds_once(client, tmp_path, monkeypatch,
                                                   isolated_store):
    from saathi import auth_bootstrap
    token = arm(monkeypatch, tmp_path)
    r = client.post("/api/v1/auth/bootstrap", json=boot_body(token))
    assert r.status_code == 200 and r.json()["ok"] is True
    assert auth_bootstrap.auth_state(isolated_store) is auth_bootstrap.AuthState.ACTIVE


def test_11_password_stored_only_as_scrypt(client, tmp_path, monkeypatch, isolated_store):
    token = arm(monkeypatch, tmp_path)
    client.post("/api/v1/auth/bootstrap", json=boot_body(token))
    owner = isolated_store.owner_id()
    stored = isolated_store.latest_password(owner)["hash"]
    assert stored.startswith("scrypt$")
    assert SYNTHETIC_PASSWORD not in stored


def test_12_no_plaintext_password_anywhere(client, tmp_path, monkeypatch, isolated_store):
    token = arm(monkeypatch, tmp_path)
    client.post("/api/v1/auth/bootstrap", json=boot_body(token))
    # every value in every table of the store
    for (table,) in isolated_store.db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall():
        for row in isolated_store.db.execute(f'SELECT * FROM "{table}"').fetchall():
            for value in tuple(row):
                assert SYNTHETIC_PASSWORD != value
                if isinstance(value, str):
                    assert SYNTHETIC_PASSWORD not in value
    # and no dotenv was written
    from saathi.dotenv_policy import HISTORICAL_DOTENV
    if HISTORICAL_DOTENV.exists():
        assert SYNTHETIC_PASSWORD not in HISTORICAL_DOTENV.read_text()


def test_13_operator_token_never_persisted(client, tmp_path, monkeypatch, isolated_store):
    token = arm(monkeypatch, tmp_path)
    client.post("/api/v1/auth/bootstrap", json=boot_body(token))
    for (table,) in isolated_store.db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall():
        for row in isolated_store.db.execute(f'SELECT * FROM "{table}"').fetchall():
            for value in tuple(row):
                if isinstance(value, str):
                    assert token not in value


def test_14_session_issued_only_after_commit(client, tmp_path, monkeypatch, isolated_store):
    token = arm(monkeypatch, tmp_path)
    r = client.post("/api/v1/auth/bootstrap", json=boot_body(token))
    assert r.json().get("token")
    # the owner and the marker exist, so the session cannot predate them
    assert isolated_store.bootstrap_completed() is not None
    assert isolated_store.credential_census()["sessions"] >= 1


def test_15_failed_transaction_leaves_no_partial_owner(tmp_path, monkeypatch, isolated_store):
    """A policy failure must not leave a half-built owner behind."""
    from saathi import auth_bootstrap
    arm(monkeypatch, tmp_path)
    with pytest.raises(auth_bootstrap.BootstrapError):
        auth_bootstrap.bootstrap_owner(isolated_store, password="weak",
                                       operator_token="irrelevant")
    census = isolated_store.credential_census()
    assert census["users"] == 0 and census["passwords"] == 0
    assert isolated_store.bootstrap_completed() is None


def test_16_concurrent_bootstrap_has_exactly_one_winner(tmp_path, monkeypatch,
                                                        isolated_store):
    from saathi import auth_bootstrap
    token = arm(monkeypatch, tmp_path)
    # The limiter is not what is under test here, but raise it through
    # monkeypatch so the change is undone: a bare assignment leaks a 50-attempt
    # ceiling into every later test in the session, including the one whose
    # whole subject is that the ceiling is low.
    monkeypatch.setattr(auth_bootstrap, "MAX_ATTEMPTS", 50)
    results: list[object] = []
    lock = threading.Lock()

    def attempt():
        try:
            oid = auth_bootstrap.bootstrap_owner(
                isolated_store, password=SYNTHETIC_PASSWORD, operator_token=token)
            with lock:
                results.append(oid)
        except auth_bootstrap.BootstrapError as exc:
            with lock:
                results.append(exc.code)

    threads = [threading.Thread(target=attempt) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    winners = [r for r in results if isinstance(r, str) and len(r) == 32
               and not r.startswith("BOOTSTRAP_")]
    assert len(winners) == 1, results
    assert isolated_store.credential_census()["users"] == 1


def test_17_replay_denied(client, tmp_path, monkeypatch):
    token = arm(monkeypatch, tmp_path)
    assert client.post("/api/v1/auth/bootstrap", json=boot_body(token)).status_code == 200
    again = client.post("/api/v1/auth/bootstrap", json=boot_body(token))
    assert again.status_code == 403
    assert again.json()["error"] == "BOOTSTRAP_ALREADY_COMPLETE"


def test_18_restart_after_success_remains_closed(tmp_path, monkeypatch, isolated_store):
    from saathi import auth_bootstrap
    from saathi.security.store import SecurityStore
    token = arm(monkeypatch, tmp_path)
    auth_bootstrap.bootstrap_owner(isolated_store, password=SYNTHETIC_PASSWORD,
                                   operator_token=token)
    reopened = SecurityStore(db_path=tmp_path / "security.db")
    try:
        assert auth_bootstrap.auth_state(reopened) is auth_bootstrap.AuthState.ACTIVE
        with pytest.raises(auth_bootstrap.BootstrapError) as exc:
            auth_bootstrap.bootstrap_owner(reopened, password=SYNTHETIC_PASSWORD,
                                           operator_token=token)
        assert exc.value.code == "BOOTSTRAP_ALREADY_COMPLETE"
    finally:
        reopened.close()


# ── 19-20: legacy routes ────────────────────────────────────────────────────

def test_19_change_password_cannot_bootstrap(client):
    r = client.post("/api/v1/auth/change-password",
                    json={"current": "", "new_password": SYNTHETIC_PASSWORD})
    assert r.status_code == 410
    assert r.json()["error"] == "LEGACY_AUTH_RETIRED"
    assert "token" not in r.json()
    assert "baadar_session" not in r.cookies


def test_20_reset_cannot_bootstrap_or_write_dotenv(client):
    from saathi.dotenv_policy import HISTORICAL_DOTENV
    before = HISTORICAL_DOTENV.read_bytes() if HISTORICAL_DOTENV.exists() else None
    r = client.post("/api/v1/auth/reset",
                    json={"token": "x", "new_password": SYNTHETIC_PASSWORD})
    assert r.status_code == 410
    after = HISTORICAL_DOTENV.read_bytes() if HISTORICAL_DOTENV.exists() else None
    assert after == before


def test_20b_login_cannot_bootstrap(client, isolated_store):
    """The 'nothing configured -> let the owner in' branch is gone."""
    r = client.post("/api/v1/auth/login", json={"password": "literally anything"})
    assert r.status_code == 409
    assert r.json()["error"] == "NOT_INITIALIZED"
    assert isolated_store.credential_census()["sessions"] == 0


# ── 21-25: no authority, and no minting, before ACTIVE ──────────────────────

PROTECTED = [
    ("get", "/api/v1/events/recent"),
    ("get", "/api/v1/auth/sessions"),
    ("post", "/api/v1/connectors/execute"),
]


@pytest.mark.parametrize("method,path", PROTECTED)
def test_21_local_caller_without_session_denied(client, method, path):
    r = getattr(client, method)(path, **({"json": {}} if method == "post" else {}))
    assert r.status_code in (401, 404, 409), (path, r.status_code)


def test_22_absent_password_hash_grants_nothing(client, monkeypatch):
    import saathi.server as svr
    monkeypatch.setattr(svr, "_PASSWORD_HASH", "", raising=False)

    class _Req:
        cookies: dict = {}
        headers: dict = {}
        client = type("C", (), {"host": "127.0.0.1"})()

    assert svr._is_authed(_Req()) is False


def test_23_api_token_minting_denied_before_active(client):
    r = client.post("/api/v1/security/tokens",
                    json={"name": "x", "purpose": "", "permissions": [],
                          "expires_in_days": 30})
    assert r.status_code in (401, 409)
    assert "token" not in r.json()


def test_23b_token_minting_gate_is_independent_of_is_authed(client, monkeypatch):
    """The ACTIVE gate must hold on its own, not only because auth fails.

    ``_is_authed`` already refuses outside ACTIVE, so a plain unauthenticated
    request cannot tell the two defences apart -- and a mutation that deletes
    the gate survives. Authentication is forced True here so the gate is the
    only thing left standing.
    """
    import saathi.server as svr
    monkeypatch.setattr(svr, "_is_authed", lambda request: True)
    r = client.post("/api/v1/security/tokens",
                    json={"name": "x", "purpose": "", "permissions": [],
                          "expires_in_days": 30})
    assert r.status_code == 409
    assert r.json()["error"] == "NOT_INITIALIZED"
    assert "token" not in r.json()


def test_23c_passkey_and_rotate_gates_are_independent(client, monkeypatch):
    import saathi.server as svr
    monkeypatch.setattr(svr, "_is_authed", lambda request: True)
    assert client.post("/api/v1/auth/passkey/register/options", json={}).status_code == 409
    assert client.post("/api/v1/auth/passkey/register/verify", json={}).status_code == 409
    assert client.post("/api/v1/auth/session/rotate", json={}).status_code == 409


def test_24_passkey_registration_denied_before_active(client):
    r = client.post("/api/v1/auth/passkey/register/options", json={})
    assert r.status_code == 409
    r2 = client.post("/api/v1/auth/passkey/register/verify", json={})
    assert r2.status_code == 409


def test_25_session_rotation_denied_before_active(client):
    r = client.post("/api/v1/auth/session/rotate", json={})
    assert r.status_code in (401, 409)


# ── 26-29: contamination ────────────────────────────────────────────────────

def _plant_owner(store) -> str:
    """Write a users row the way something hostile would.

    Deliberately not ``get_or_create_owner``: that no longer creates an owner
    before bootstrap, which is the point of test 53. Planting has to bypass the
    application to describe what an attacker with store access can leave behind.
    """
    import time as _t
    uid = secrets.token_hex(16)
    store.db.execute(
        "INSERT INTO users (id, email, name, created_at, updated_at) VALUES (?,?,?,?,?)",
        (uid, None, "planted", _t.time(), _t.time()))
    store.db.commit()
    return uid


def _plant_session(store) -> str:
    from saathi import sessions
    uid = _plant_owner(store)
    raw = secrets.token_urlsafe(32)
    store.session_create(user_id=uid, token_hash=sessions._hash(raw),
                         expires_at=2**31)
    return raw


def test_26_contaminated_state_refuses_bootstrap(tmp_path, monkeypatch, isolated_store):
    from saathi import auth_bootstrap
    _plant_session(isolated_store)
    assert auth_bootstrap.auth_state(isolated_store) is \
        auth_bootstrap.AuthState.CONTAMINATED_UNINITIALIZED
    token = arm(monkeypatch, tmp_path)
    with pytest.raises(auth_bootstrap.BootstrapError) as exc:
        auth_bootstrap.bootstrap_owner(isolated_store, password=SYNTHETIC_PASSWORD,
                                       operator_token=token)
    assert exc.value.code == "BOOTSTRAP_CONTAMINATED_STATE"


def test_26b_contaminated_state_is_not_cleaned_up(tmp_path, monkeypatch, isolated_store):
    """Evidence survives the refusal — nothing is silently deleted."""
    from saathi import auth_bootstrap
    _plant_session(isolated_store)
    before = isolated_store.credential_census()
    arm(monkeypatch, tmp_path)
    with pytest.raises(auth_bootstrap.BootstrapError):
        auth_bootstrap.bootstrap_owner(isolated_store, password=SYNTHETIC_PASSWORD,
                                       operator_token="x")
    assert isolated_store.credential_census() == before


def test_27_planted_session_cannot_authenticate(client, isolated_store):
    raw = _plant_session(isolated_store)
    client.cookies.set("baadar_session", raw)
    r = client.get("/api/v1/auth/sessions")
    assert r.status_code in (401, 404, 409)


def test_28_planted_api_token_cannot_authenticate(client, isolated_store):
    from saathi.security.registry import get_registry
    uid = _plant_owner(isolated_store)
    _tid, raw = get_registry().create(uid, "planted", purpose="", permissions=[],
                                      expires_in_days=30)
    r = client.get("/api/v1/auth/sessions", headers={"x-saathi-token": raw})
    assert r.status_code in (401, 404, 409)


def test_29_planted_passkey_cannot_authenticate(client, isolated_store):
    isolated_store.passkey_save(_plant_owner(isolated_store),
                                credential_id="planted", public_key="x",
                                rp_id="localhost", sign_count=0)
    r = client.post("/api/v1/auth/passkey/login/verify", json={})
    assert r.status_code == 409


# ── 30-33: ACTIVE behaves, and voice never authenticates ────────────────────

def _bootstrap(client, tmp_path, monkeypatch):
    token = arm(monkeypatch, tmp_path)
    r = client.post("/api/v1/auth/bootstrap", json=boot_body(token))
    assert r.status_code == 200
    return r.json()["token"]


def test_30_active_credentials_work(client, tmp_path, monkeypatch):
    _bootstrap(client, tmp_path, monkeypatch)
    login = client.post("/api/v1/auth/login", json={"password": SYNTHETIC_PASSWORD})
    assert login.status_code == 200 and login.json()["ok"] is True
    bad = client.post("/api/v1/auth/login", json={"password": "wrong-password"})
    assert bad.status_code == 401


def test_31_revoked_session_denied(client, tmp_path, monkeypatch):
    from saathi import sessions
    token = _bootstrap(client, tmp_path, monkeypatch)
    sessions.revoke(sessions.session_id(token))
    client.cookies.set("baadar_session", token)
    r = client.get("/api/v1/auth/sessions")
    assert r.status_code in (401, 404)


def test_32_voice_command_requires_authentication(client):
    r = client.post("/api/v1/voice/command", files={"file": ("a.wav", b"RIFF", "audio/wav")})
    assert r.status_code in (401, 409, 422)


def test_33_speaker_identity_cannot_authenticate(client, isolated_store):
    """No speaker/voice signal is consulted anywhere in the auth decision."""
    import inspect
    import saathi.server as svr
    src = inspect.getsource(svr._is_authed)
    for word in ("speaker", "voice", "face", "enroll"):
        assert word not in src.lower()


# ── 34-38: the authority boundary is unchanged ──────────────────────────────

def test_35_execution_gateway_still_fails_closed():
    from saathi.tools.registry import execute_tool
    out = execute_tool("send_email", {"to": "a@b.c", "subject": "s", "body": "b"})
    assert out.get("blocked") or out.get("error")
    assert "approval" in str(out).lower() or "gateway" in str(out).lower()


def test_36_approval_reference_is_server_minted_only():
    from saathi.tool_runtime.compat import try_canonical_legacy_tool
    out = try_canonical_legacy_tool("send_email",
                                    {"to": "a@b.c", "subject": "s", "body": "b"})
    assert out is None or out.get("error") == "approval_required"


def test_37_financial_and_account_change_ops_remain_blocked():
    from saathi.connectors.gov.side_effects import (
        ACCOUNT_CHANGE_OPERATIONS, FINANCIAL_OPERATIONS,
    )
    assert "change_password" in ACCOUNT_CHANGE_OPERATIONS
    assert "grant_admin" in ACCOUNT_CHANGE_OPERATIONS
    assert "transfer" in FINANCIAL_OPERATIONS


def test_38_trading_guardian_unchanged():
    from saathi.platform.tg import LIVE_TRADING_AUTHORIZED
    assert LIVE_TRADING_AUTHORIZED is False


# ── 39-42: allowlist, CSRF/origin, rate limiting, output hygiene ────────────

def test_39_public_allowlist_has_no_unauthorized_mutation():
    """Only bootstrap may change state without authentication."""
    import inspect
    import saathi.server as svr
    src = inspect.getsource(svr._auth)
    assert '"/api/v1/auth/change-password"' not in src
    assert '"/api/v1/auth/reset"' not in src
    assert 'path.startswith("/api/v1/auth/reset")' not in src
    assert '"/api/v1/auth/bootstrap"' in src


def test_40_disallowed_origin_rejected(client, tmp_path, monkeypatch):
    token = arm(monkeypatch, tmp_path)
    r = client.post("/api/v1/auth/bootstrap", json=boot_body(token),
                    headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
    assert r.json()["error"] == "BOOTSTRAP_ORIGIN_REJECTED"


def test_41_rate_limiter_ignores_forwarded_ip(tmp_path, monkeypatch, isolated_store):
    """The old limiter keyed on x-forwarded-for and was bypassable per header."""
    from saathi import auth_bootstrap
    arm(monkeypatch, tmp_path)
    auth_bootstrap.reset_rate_limit_for_tests()
    codes = []
    # Bounded by a literal rather than by MAX_ATTEMPTS: reading the constant
    # makes the loop grow with any ceiling somebody raises, so a limiter weakened
    # to a billion attempts turns this test into a hang instead of a failure.
    for _ in range(22):
        try:
            auth_bootstrap.bootstrap_owner(isolated_store, password=SYNTHETIC_PASSWORD,
                                           operator_token="wrong")
        except auth_bootstrap.BootstrapError as exc:
            codes.append(exc.code)
    assert "BOOTSTRAP_RATE_LIMITED" in codes


def test_42_refusals_leak_no_secret(client, tmp_path, monkeypatch):
    token = arm(monkeypatch, tmp_path)
    for body in ({"operator_token": "wrong", "new_password": SYNTHETIC_PASSWORD},
                 {"operator_token": token, "new_password": "weak"}):
        r = client.post("/api/v1/auth/bootstrap", json=body)
        text = r.text
        assert token not in text
        assert SYNTHETIC_PASSWORD not in text


# ── static invariant: dotenv must never carry password material again ───────

def test_43_no_password_is_ever_written_through_dotenv():
    """A grep-level invariant, so a reintroduction fails here rather than in prod.

    Both retired routes persisted the new password as cleartext in the
    checkout's ``.env``. Routing that through ``dotenv_policy`` made the write
    *controllable*, not acceptable -- a credential does not belong in a dotenv
    file at all. This asserts no caller passes password-shaped material to the
    dotenv writer.
    """
    import re
    root = pathlib.Path(__file__).resolve().parent.parent / "saathi"
    offenders = []
    pattern = re.compile(r"write_dotenv_values\s*\(([^)]*)\)", re.S)
    for py in root.rglob("*.py"):
        for call in pattern.findall(py.read_text(errors="ignore")):
            if re.search(r"password", call, re.I):
                offenders.append(f"{py.relative_to(root)}: {call.strip()[:60]}")
    assert offenders == [], offenders


def test_44_retired_routes_have_no_password_writer_left():
    """The retired handlers must contain no credential machinery.

    Their docstrings deliberately name the old mechanism, so the check inspects
    executable statements only -- an assertion that reads the prose would pass
    or fail on how the vulnerability is described rather than on what the code
    does.
    """
    import ast
    import inspect
    import saathi.server as svr

    banned = ("write_dotenv_values", "_PASSWORD_HASH", "_RAW_PASSWORD",
              "sessions.create", "set_cookie", "hash_password")
    for name in ("change_password_retired", "reset_password_retired"):
        tree = ast.parse(inspect.getsource(getattr(svr, name)).strip())
        fn = tree.body[0]
        body = fn.body[1:] if (fn.body and isinstance(fn.body[0], ast.Expr)
                               and isinstance(fn.body[0].value, ast.Constant)) else fn.body
        code = "\n".join(ast.dump(node) for node in body)
        for token in banned:
            assert token not in code, f"{name} still references {token}"


# ── 45-49: loopback is not identity anywhere, not only inside _is_authed ────
#
# The first pass of this repair deleted the ``_is_local`` fallback from
# ``_is_authed`` and stopped there. Eight call sites still read
# ``_is_authed(request) or _is_local(request)``, so the same "the caller is on
# this machine, therefore the caller is the owner" rule survived one function
# further out -- on passkey registration, which mints a durable credential, and
# on a file read that takes the path from the caller. Removing a fallback from
# the predicate is not the same as removing it from the decisions.

def test_45_no_endpoint_falls_back_to_loopback_identity():
    """No authorization decision may consult ``_is_local``."""
    import ast
    import inspect
    import saathi.server as svr

    tree = ast.parse(inspect.getsource(svr))
    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name == "_is_local":
            continue
        for call in ast.walk(node):
            if isinstance(call, ast.Call) and isinstance(call.func, ast.Name) \
                    and call.func.id == "_is_local":
                offenders.append(f"{node.name}:{call.lineno}")
    assert offenders == [], offenders


@pytest.mark.parametrize("path", [
    "/api/v1/auth/passkey/register/options",
    "/api/v1/auth/passkey/register/verify",
])
def test_46_passkey_registration_denied_to_loopback_without_session(
        client, tmp_path, monkeypatch, path):
    """Even ACTIVE, an unauthenticated on-box caller may not mint a passkey."""
    _bootstrap(client, tmp_path, monkeypatch)
    client.cookies.clear()
    r = client.post(path, json={})
    assert r.status_code == 401, r.status_code


def test_47_signed_in_is_not_inferred_from_loopback(client, tmp_path, monkeypatch):
    """The public shell status must not tell an anonymous caller it is signed in."""
    r = client.get("/api/v1/auth/passkey/status")
    assert r.status_code == 200 and r.json()["signed_in"] is False

    _bootstrap(client, tmp_path, monkeypatch)
    client.cookies.clear()
    r = client.get("/api/v1/auth/passkey/status")
    assert r.json()["signed_in"] is False


def test_48_voice_principal_is_never_a_loopback_constant(client):
    """A credential-less caller gets no principal, so no session scope."""
    import saathi.server as svr

    class _Req:
        cookies: dict = {}
        headers: dict = {}
        class client:  # noqa: N801 - mimics starlette's request.client
            host = "127.0.0.1"

    assert svr._voice_principal(_Req()) == ""
    assert "local" not in inspect_source(svr._voice_principal)


def inspect_source(fn) -> str:
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(fn).strip())
    node = tree.body[0]
    body = node.body[1:] if (node.body and isinstance(node.body[0], ast.Expr)
                             and isinstance(node.body[0].value, ast.Constant)) else node.body
    return "\n".join(ast.dump(n) for n in body)


def test_49_deterministic_session_token_is_gone(client, tmp_path, monkeypatch):
    """``sha256(":baadar-session")`` was a valid session on a bootstrapped system.

    ``_session_token()`` seeded itself from ``_PASSWORD_HASH or ACCESS_TOKEN or
    ""``. Secure bootstrap writes the credential to the security store and
    leaves both process globals empty, so the value reduced to the hash of a
    fixed string -- a credential with no secret in it, accepted by ``_is_authed``
    on a system that had just been correctly initialised.
    """
    import hashlib
    import saathi.server as svr

    assert not hasattr(svr, "_session_token")
    _bootstrap(client, tmp_path, monkeypatch)
    client.cookies.clear()
    forged = hashlib.sha256(b":baadar-session").hexdigest()
    r = client.get("/api/v1/auth/sessions", headers={"x-baadar-session": forged})
    assert r.status_code == 401


def test_50_arbitrary_path_download_requires_a_session(client, tmp_path, monkeypatch):
    """The studio download reads a caller-supplied path; loopback is not enough."""
    _bootstrap(client, tmp_path, monkeypatch)
    client.cookies.clear()
    r = client.get("/api/v1/studio/download", params={"path": "/etc/hosts"})
    assert r.status_code == 401


# ── 51-53: an uninitialised system must not contaminate itself ──────────────

def test_51_public_reads_do_not_contaminate_an_uninitialised_store(
        client, tmp_path, monkeypatch, isolated_store):
    """The unlock screen's own requests must leave bootstrap possible.

    ``get_or_create_owner`` manufactured a users row for any caller that asked
    who the owner was -- and ``/api/v1/auth/passkey/status``, which the unlock
    screen calls before anybody has signed in, asks. One anonymous GET therefore
    moved a fresh install from UNINITIALIZED to CONTAMINATED_UNINITIALIZED,
    where bootstrap is refused: a denial of service against installation itself,
    reachable by any unauthenticated caller.
    """
    from saathi import auth_bootstrap

    for _ in range(3):
        assert client.get("/api/v1/auth/passkey/status").status_code == 200
        client.get("/api/v1/auth/bootstrap/status")
    assert isolated_store.credential_census()["users"] == 0
    assert auth_bootstrap.auth_state(isolated_store) is not \
        auth_bootstrap.AuthState.CONTAMINATED_UNINITIALIZED

    token = arm(monkeypatch, tmp_path)
    assert client.post("/api/v1/auth/bootstrap",
                       json=boot_body(token)).status_code == 200


def test_52_legacy_migration_plants_nothing_before_bootstrap(tmp_path, monkeypatch):
    """``get_store()`` migrates on first access, in every process, unconditionally.

    On an uninitialised install that ran before anyone had authenticated: it
    created an owner and imported legacy sessions and passkeys behind it. The
    result was a store the server had planted credentials into itself.
    """
    import json

    state = tmp_path / "legacy-state"
    state.mkdir()
    monkeypatch.setenv("SAATHI_STATE_ROOT", str(state))
    (state / "sessions.json").write_text(json.dumps(
        [{"id": "legacy1", "th": "deadbeef", "kind": "password", "created": 1.0}]))
    (state / "passkeys.json").write_text(json.dumps(
        [{"credential_id": "legacy-pk", "public_key": "x", "rp_id": "localhost"}]))

    from saathi.security import store as store_mod
    store_mod.close_store()
    store_mod._default_store = None
    fresh = store_mod.get_store(db_path=tmp_path / "legacy.db")
    try:
        census = fresh.credential_census()
        assert census["users"] == 0 and census["sessions"] == 0 and census["passkeys"] == 0
    finally:
        store_mod.close_store()
        store_mod._default_store = None


def test_53_owner_creation_is_bootstrap_only(isolated_store):
    """Nothing but bootstrap may bring the owner identity into existence."""
    assert isolated_store.get_or_create_owner() == ""
    assert isolated_store.credential_census()["users"] == 0


# ── 54-57: the four properties that survived a mutation pass ────────────────

def test_54_bootstrap_attempts_are_actually_bounded(client, tmp_path, monkeypatch):
    """A limiter that ignores forwarded IPs still has to refuse somebody.

    Test 41 proved attempts are counted against the peer rather than a header,
    which a limiter with an effectively infinite ceiling also satisfies. The
    ceiling itself is the property: a wrong token must stop being answerable.
    """
    from saathi import auth_bootstrap

    # The bound is asserted against a literal, not against the module's own
    # constant: a test that reads MAX_ATTEMPTS to decide how many attempts to
    # make moves its goalposts with the value it is supposed to be constraining,
    # and passes just as happily when the ceiling is raised to a billion.
    CEILING = 20
    assert auth_bootstrap.MAX_ATTEMPTS <= CEILING, auth_bootstrap.MAX_ATTEMPTS

    arm(monkeypatch, tmp_path)
    codes = []
    for _ in range(CEILING + 1):
        r = client.post("/api/v1/auth/bootstrap", json=boot_body("wrong-token-value"))
        codes.append(r.json().get("error"))
    assert codes[-1] == "BOOTSTRAP_RATE_LIMITED", codes
    assert "BOOTSTRAP_TOKEN_INVALID" in codes


def test_55_operator_token_file_is_consumed_on_success(client, tmp_path, monkeypatch):
    """The token is spent, not merely outranked by the completion marker.

    Replay is refused after success because the system is ACTIVE -- which would
    remain true if the token file were left sitting on disk, live, for the next
    installation or the next reader. Consumption is a separate guarantee.
    """
    token = arm(monkeypatch, tmp_path)
    path = tmp_path / "operator.token"
    assert client.post("/api/v1/auth/bootstrap", json=boot_body(token)).status_code == 200

    assert not path.exists(), "the operator token survived the bootstrap that spent it"
    used = path.with_name(path.name + ".used")
    if used.exists():        # quarantined rather than unlinked
        assert oct(used.stat().st_mode & 0o777) == "0o600"


def test_56_voice_turn_denies_an_unauthenticated_caller_on_an_active_system(
        client, tmp_path, monkeypatch):
    """401 specifically, and before any audio is read.

    A 409 or a 422 would also be a refusal, but they are refusals for other
    reasons -- not initialised, or a malformed body -- and a check that accepts
    them cannot tell "the caller was rejected" from "the request never got that
    far". On an ACTIVE system with a well-formed upload, the only correct answer
    to a caller holding no credential is unauthorized.
    """
    _bootstrap(client, tmp_path, monkeypatch)
    client.cookies.clear()
    r = client.post("/api/v1/voice/command",
                    files={"file": ("speech.webm", b"\x1a\x45\xdf\xa3fake", "audio/webm")},
                    data={"session_id": "default"})
    assert r.status_code == 401, r.status_code


def test_57_legacy_migration_refuses_explicitly_before_bootstrap(tmp_path, monkeypatch):
    """The refusal is a decision, not an accident of foreign-key failures.

    Without the guard, migration still plants nothing -- every insert names an
    owner that does not exist and the whole thing is swallowed by a bare
    ``except``. That is not a security property, it is a coincidence, and it
    would evaporate the moment the owner row existed for another reason.
    """
    from saathi.security.store import SecurityStore

    store = SecurityStore(db_path=tmp_path / "premature.db")
    try:
        assert store.migrate_from_legacy().get("skipped") == "NOT_INITIALIZED"
    finally:
        store.close()


def test_58_voice_turn_authenticates_in_its_own_body(client, tmp_path, monkeypatch):
    """The handler's own gate, not only the middleware in front of it.

    An endpoint test cannot see this: ``/api/v1/voice/command`` is off the
    public allowlist, so the middleware answers 401 first and the handler could
    be gutted without any request-level test noticing. The gate inside the
    handler exists precisely for the case where the allowlist regresses, which
    is a thing that has happened, so it is asserted directly -- and asserted to
    come before the principal is derived, since a principal computed for an
    unauthenticated caller is a caller who has been given a scope.
    """
    import ast
    import inspect
    import saathi.server as svr

    fn = ast.parse(inspect.getsource(svr.voice_command).strip()).body[0]
    # Ordered by line, not by ``ast.walk``, which yields breadth-first and would
    # compare positions in the tree rather than in the source.
    calls = sorted(((n.lineno, n.func.id) for n in ast.walk(fn)
                    if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)))
    names = [name for _, name in calls]
    assert "_is_authed" in names, "voice_command no longer authenticates"
    assert names.index("_is_authed") < names.index("_voice_principal")

    src = inspect.getsource(svr.voice_command).lower()
    for word in ("speaker", "voiceprint", "enroll"):
        assert f"if {word}" not in src
