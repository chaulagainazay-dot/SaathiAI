"""M15.3 enterprise connector platform — unit + security + engine-wiring tests."""
import tempfile

import pytest

from saathi.connectors.platform import store as S
from saathi.connectors.platform.execution import ExecutionEngine, ExecRequest
from saathi.connectors.platform.enterprise import scopes, oauth, resilience, errors, live_validation
from saathi.connectors.platform.enterprise.oauth import OAuthFlow, OAuthError, OAuthState


@pytest.fixture
def eng():
    return ExecutionEngine(store=S.ConnectorStore(tempfile.mktemp(suffix=".db")))


# ── scope engine ────────────────────────────────────────────────────────────
def test_scope_exact_match_missing():
    d = scopes.evaluate(tool_id="gmail.send_email",
                        account={"owner": "a", "connector_id": "gmail", "state": "healthy",
                                 "enabled": 1, "granted_scopes": ["gmail.readonly"]})
    assert not d.allowed and d.reason_code == scopes.R_SCOPE_MISSING
    assert d.required_scopes == ["gmail.send"]


def test_scope_granted_allows():
    d = scopes.evaluate(tool_id="gmail.send_email",
                        account={"owner": "a", "connector_id": "gmail", "state": "healthy",
                                 "enabled": 1, "granted_scopes": ["gmail.send"]})
    assert d.allowed


def test_scope_revoked_account_denied():
    d = scopes.evaluate(tool_id="github.list_issues",
                        account={"owner": "a", "connector_id": "github", "state": "revoked",
                                 "enabled": 1})
    assert not d.allowed and d.reason_code == scopes.R_ACCOUNT_REVOKED


def test_scope_untracked_account_not_scope_blocked():
    # deterministic/local accounts (no granted_scopes) are not scope-blocked
    d = scopes.evaluate(tool_id="github.list_issues",
                        account={"owner": "a", "connector_id": "github", "state": "healthy",
                                 "enabled": 1})
    assert d.allowed


def test_scope_agent_risk4_manual_only():
    d = scopes.evaluate(tool_id="deploy.deploy_to_production",
                        account={"owner": "a", "connector_id": "deploy", "state": "healthy",
                                 "enabled": 1}, actor_type="agent")
    assert not d.allowed and d.reason_code == scopes.R_MANUAL_ONLY


# ── OAuth lifecycle security ────────────────────────────────────────────────
def test_oauth_begin_sets_state_pkce():
    f = OAuthFlow("gmail", "ajay", "https://localhost/cb", ["gmail.readonly"])
    p = f.begin()
    assert p["state"] and p["code_challenge"] and p["code_challenge_method"] == "S256"
    assert f.status == OAuthState.AUTHORIZATION_PENDING.value


def test_oauth_state_mismatch_blocked():
    f = OAuthFlow("gmail", "ajay", "https://localhost/cb", ["gmail.readonly"])
    f.begin()
    with pytest.raises(OAuthError) as e:
        f.handle_callback(state="wrong", code="c", redirect_uri="https://localhost/cb", owner="ajay")
    assert e.value.code == "invalid_callback"


def test_oauth_redirect_uri_mismatch_blocked():
    f = OAuthFlow("gmail", "ajay", "https://localhost/cb", ["gmail.readonly"])
    p = f.begin()
    with pytest.raises(OAuthError):
        f.handle_callback(state=p["state"], code="c", redirect_uri="https://evil/cb", owner="ajay")


def test_oauth_wrong_user_blocked():
    f = OAuthFlow("gmail", "victim", "https://localhost/cb", ["gmail.readonly"])
    p = f.begin()
    with pytest.raises(OAuthError):
        f.handle_callback(state=p["state"], code="c", redirect_uri="https://localhost/cb", owner="attacker")


def test_oauth_scope_expansion_blocked():
    f = OAuthFlow("gmail", "ajay", "https://localhost/cb", ["gmail.readonly"])
    p = f.begin()
    with pytest.raises(OAuthError) as e:
        f.handle_callback(state=p["state"], code="c", redirect_uri="https://localhost/cb",
                          owner="ajay",
                          exchange=lambda code, v: {"scope": "gmail.readonly gmail.send", "expires_in": 3600})
    assert e.value.code == "scope_expansion_blocked"


def test_oauth_refresh_no_widen():
    f = OAuthFlow("gmail", "ajay", "https://localhost/cb", ["gmail.readonly"])
    f.begin()
    with pytest.raises(OAuthError) as e:
        f.refresh(previous_granted=["gmail.readonly"],
                  do_refresh=lambda: {"scope": "gmail.readonly gmail.send"})
    assert e.value.code == "scope_widening_blocked"


def test_oauth_exchange_env_blocked_honest():
    f = OAuthFlow("gmail", "ajay", "https://localhost/cb", ["gmail.readonly"])
    p = f.begin()
    out = f.handle_callback(state=p["state"], code="c", redirect_uri="https://localhost/cb", owner="ajay")
    assert out["live_exchange"] == "environment_blocked"


# ── circuit breaker + rate limiter ──────────────────────────────────────────
def test_circuit_opens_and_half_open_recovers():
    b = resilience.CircuitBreaker(key="k", failure_threshold=3, cooldown_sec=10)
    clk = [0.0]
    for _ in range(3):
        b.record(success=False, clock=lambda: clk[0])
    assert not b.allow(clock=lambda: clk[0])          # open
    clk[0] = 11
    assert b.allow(clock=lambda: clk[0])              # half-open probe allowed
    b.record(success=True, clock=lambda: clk[0])
    assert b.state == "closed"


def test_circuit_scoped_per_account():
    reg = resilience.BreakerRegistry()
    a = reg.get(connector_id="github", account_id="acct1", operation="op")
    b = reg.get(connector_id="github", account_id="acct2", operation="op")
    assert a.key != b.key   # one failing account does not trip the other


def test_rate_limiter_layered():
    rl = resilience.RateLimiter(limit=2, window_sec=100)
    clk = [0.0]
    r1 = rl.layered_check(user="u", connector="c", account="a", operation="o", clock=lambda: clk[0])
    r2 = rl.layered_check(user="u", connector="c", account="a", operation="o", clock=lambda: clk[0])
    r3 = rl.layered_check(user="u", connector="c", account="a", operation="o", clock=lambda: clk[0])
    assert r1["allowed"] and r2["allowed"] and not r3["allowed"]


# ── error taxonomy ──────────────────────────────────────────────────────────
def test_error_taxonomy_redacts_and_classifies():
    e = errors.normalize(category="rate_limited", detail="token=sk-secret123", provider_code="429")
    assert e["retryable"] is True and "sk-secret123" not in str(e)


def test_error_unknown_category_internal():
    e = errors.normalize(category="weird")
    assert e["code"] == "internal_error"


# ── live validation honesty ─────────────────────────────────────────────────
def test_verification_matrix_no_fake_live():
    m = live_validation.verification_matrix()
    assert all(r["live_tested"] is False for r in m)   # nothing live in this env
    gmail = [r for r in m if r["connector_id"] == "gmail"][0]
    assert gmail["environment_blocked"] is True


def test_ci_safe_run_no_live_calls(eng):
    out = live_validation.run_ci_safe(engine=eng)
    assert out["ran"] >= 1 and "environment_blocked" in out["live_modes"]


# ── engine wiring: scope denial + account substitution (security) ───────────
def test_engine_denies_missing_scope(eng):
    aid = eng.store.add_account(owner="ajay", connector_id="gmail", label="g", state="healthy")
    # grant only readonly, then attempt a send (needs gmail.send)
    eng.store.set_account_state(aid, "healthy")
    import json as _j
    with eng.store._conn() as c:
        c.execute("UPDATE account SET label=? WHERE id=?", ("g", aid))
    # inject granted scopes via credential-less account row update
    with eng.store._conn() as c:
        try:
            c.execute("ALTER TABLE account ADD COLUMN granted_scopes TEXT")
        except Exception:
            pass
        c.execute("UPDATE account SET granted_scopes=? WHERE id=?", (_j.dumps(["gmail.readonly"]), aid))
    r = eng.execute(ExecRequest(owner="ajay", tool_id="gmail.send_email", account_id=aid,
                                args={"text": "hi"}))
    assert r.status == "blocked"


def test_engine_account_substitution_after_approval(eng):
    a = eng.store.add_account(owner="ajay", connector_id="github", label="a", state="healthy")
    b = eng.store.add_account(owner="ajay", connector_id="github", label="b", state="healthy")
    appr = eng.request_approval(ExecRequest(owner="ajay", tool_id="github.create_issue",
                                            account_id=a, args={"title": "x"}))
    eng.store.resolve_approval(appr["approval_id"], approved=True, actor="ajay")
    r = eng.execute(ExecRequest(owner="ajay", tool_id="github.create_issue", account_id=b,
                                args={"title": "x"}, approval_id=appr["approval_id"]))
    assert r.status == "approval_required"   # approval bound to account a, not b
