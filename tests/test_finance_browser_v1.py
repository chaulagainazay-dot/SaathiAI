"""M — SAATHIOS_FINANCIAL_BROWSER security-contract tests (Phase 44).

Pure/offline. Proves owner/agent separation, interaction modes, prohibited-action blocking,
credential-field redaction, cookie/secret non-exposure, provider isolation, session expiry/
reauth, kill switch, audit redaction, PortfolioSnapshot validity + currency separation, and
that no execution path exists in the finance package.
"""
from __future__ import annotations

import time
from decimal import Decimal

from saathi.platform.finance import audit
from saathi.platform.finance.capability_matrix import CAPABILITY_MATRIX
from saathi.platform.finance.policy import (
    ALLOWED_AGENT_READS, PROHIBITED_AGENT_ACTIONS, POLICIES, Actor, FieldClass,
    InteractionMode, Provider, classify_field, enforce, is_agent_action_allowed,
    is_owner_private, redact,
)
from saathi.platform.finance.portfolio import (
    FXObservation, PortfolioSnapshot, PortfolioSourceType, Position, UnifiedPortfolioView,
    snapshot_metrics,
)
from saathi.platform.finance.session import (
    FinancialBrowserManager, SecurityState, SessionAuthState,
)


# 1 — capability matrix present for all providers, no guesses (UNKNOWN allowed)
def test_capability_matrix():
    for p in ("NEPSE", "TMS", "BINANCE", "PORTFOLIO_TRACKER"):
        assert p in CAPABILITY_MATRIX
        assert CAPABILITY_MATRIX[p]["agent_actions"] == "PROHIBITED_AGENT_ACTION"
    assert CAPABILITY_MATRIX["BINANCE"]["account_data"] == "UNKNOWN"   # not implemented → honest
    assert CAPABILITY_MATRIX["TMS"]["account_data"] == "OWNER_BROWSER_SESSION"


# 2 — domain allowlist
def test_domain_allowlist():
    pol = POLICIES[Provider.NEPSE]
    assert pol.domain_allowed("nepalstock.com") and pol.domain_allowed("www.nepalstock.com")
    assert not pol.domain_allowed("evil.example")
    assert not POLICIES[Provider.BINANCE].domain_allowed("nepalstock.com")


# 3 — owner vs agent enforcement
def test_owner_vs_agent():
    assert enforce(Actor.OWNER_INPUT, "BUY", Provider.BINANCE)[0] is True     # owner may
    assert enforce(Actor.AGENT_INPUT, "BUY", Provider.BINANCE)[0] is False    # agent may not
    assert enforce(Actor.AGENT_INPUT, "READ_PORTFOLIO", Provider.BINANCE) == (True, "AGENT_READ_ONLY")
    assert enforce(Actor.AGENT_INPUT, "FROBNICATE", Provider.NEPSE)[0] is False  # default-deny


# 4 — every prohibited action blocked for agent
def test_all_prohibited_blocked():
    for act in PROHIBITED_AGENT_ACTIONS:
        assert enforce(Actor.AGENT_INPUT, act, Provider.BINANCE)[0] is False
        assert not is_agent_action_allowed(act)
    for r in ALLOWED_AGENT_READS:
        assert is_agent_action_allowed(r)


# 5 — credential fields → OWNER_PRIVATE_INPUT
def test_credential_field_classification():
    for f in ("password", "login_password", "otp", "otp_code", "2fa", "totp", "cvv", "pin",
              "api_key", "api_secret", "private_key", "seed_phrase", "recovery_code",
              "security_answer", "mcp_token"):
        assert is_owner_private(f), f
    assert classify_field("account_balance") == FieldClass.SENSITIVE_READABLE
    assert classify_field("company_name") == FieldClass.PUBLIC_READABLE


# 6 — redaction of secrets / OTP
def test_redaction():
    assert "abcdef1234567890abcdef1234" not in redact("api_key=abcdef1234567890abcdef1234")
    assert "Bearer" in redact("Authorization: Bearer xyz") or "«redacted»" in redact("Authorization: Bearer xyz")
    assert "«redacted»" in redact("password: hunter2longenoughtoken")
    assert "123456" not in redact("your otp is 123456")


# 7 — session has NO cookie/token/secret fields
def test_session_no_secret_fields():
    m = FinancialBrowserManager()
    s = m.open(Provider.NEPSE)
    d = s.to_public()
    for bad in ("cookie", "token", "secret", "password", "api_key"):
        assert not any(bad in k.lower() for k in d), bad
    assert not any("cookie" in a.lower() or "secret" in a.lower() or "token" in a.lower()
                   for a in vars(s))


# 8 — agent read gated by owner authentication
def test_agent_read_gating():
    m = FinancialBrowserManager()
    s = m.open(Provider.PORTFOLIO_TRACKER)
    assert m.agent_read(s.session_id, "READ_PORTFOLIO")[0] is False       # not authed yet
    m.mark_authenticated(s.session_id)
    assert m.agent_read(s.session_id, "READ_PORTFOLIO")[0] is True
    assert m.agent_read(s.session_id, "BUY")[0] is False                  # action still blocked


# 9 — provider isolation
def test_provider_isolation():
    m = FinancialBrowserManager()
    a = m.open(Provider.TMS)
    b = m.open(Provider.BINANCE)
    m.mark_authenticated(a.session_id)
    m.kill(a.session_id)
    assert m.get(a.session_id).security_state == SecurityState.KILLED
    assert m.get(b.session_id).security_state != SecurityState.KILLED     # unaffected


# 10 — session expiry → OWNER_REAUTH_REQUIRED
def test_session_expiry():
    m = FinancialBrowserManager(ttl_sec=100)
    s = m.open(Provider.TMS, now=1000.0)
    m.mark_authenticated(s.session_id, now=1000.0)
    got = m.get(s.session_id, now=1000.0 + 50)
    assert got.security_state == SecurityState.CONNECTED_READ_ONLY
    got2 = m.get(s.session_id, now=1000.0 + 200)
    assert got2.security_state == SecurityState.SESSION_EXPIRED
    assert got2.auth_state == SessionAuthState.OWNER_REAUTH_REQUIRED


# 11 — kill switch revokes capability
def test_kill_switch():
    m = FinancialBrowserManager()
    s = m.open(Provider.BINANCE)
    m.mark_authenticated(s.session_id)
    assert s.read_capability == POLICIES[Provider.BINANCE].readable_regions
    m.kill(s.session_id)
    assert m.get(s.session_id).read_capability == ()
    assert m.agent_read(s.session_id, "READ_BALANCE")[0] is False


# 12 — kill_all
def test_kill_all():
    m = FinancialBrowserManager()
    m.open(Provider.NEPSE); m.open(Provider.TMS)
    assert m.kill_all() >= 2


# 13 — audit records reads without secrets
def test_audit_redaction():
    audit.clear()
    m = FinancialBrowserManager()
    s = m.open(Provider.NEPSE)
    m.mark_authenticated(s.session_id)
    m.agent_read(s.session_id, "OBSERVE_PUBLIC_PAGE")
    audit.record(provider="NEPSE", actor="AGENT_INPUT", capability="READ_QUOTE", result="OK",
                 detail="Authorization: Bearer supersecrettoken1234567890")
    t = audit.tail(10)
    assert any(r["capability"] == "OBSERVE_PUBLIC_PAGE" for r in t)
    assert all("supersecrettoken" not in r["detail"] for r in t)


# 14 — PortfolioSnapshot validity + no fabricated fields
def test_portfolio_snapshot():
    p = Position(instrument_id="NEPSE:NABIL", symbol="NABIL", asset_type="EQUITY",
                 quantity=Decimal("100"), average_cost=Decimal("500"),
                 current_price=Decimal("554"), current_price_source="OFFICIAL_PAGE_OBSERVED",
                 market_value=Decimal("55400"), cost_basis=Decimal("50000"),
                 unrealized_pnl=Decimal("5400"), currency="NPR", source="OWNER_IMPORTED")
    snap = PortfolioSnapshot(snapshot_id="s1", owner_id="owner", provider="TMS",
                             account_type="NEPSE_DEMAT", observed_at=time.time(), currency="NPR",
                             source_type=PortfolioSourceType.OWNER_IMPORTED_PORTFOLIO,
                             positions=(p,), total_market_value=Decimal("55400"))
    d = snap.to_public()
    assert d["data_class"] == "READ_ONLY_PORTFOLIO_OBSERVATION"
    assert d["positions"][0]["current_price_source"] == "OFFICIAL_PAGE_OBSERVED"
    m = snapshot_metrics(snap)
    assert m["top_concentration_pct"] == "100.00" and m["unrealized_pnl"] == "5400"


# 15 — currency separation; no cross-currency sum without sourced FX
def test_currency_separation():
    npr = PortfolioSnapshot("n", "owner", "TMS", "NEPSE_DEMAT", time.time(), "NPR",
                            PortfolioSourceType.OWNER_IMPORTED_PORTFOLIO,
                            total_market_value=Decimal("100000"))
    usd = PortfolioSnapshot("u", "owner", "BINANCE", "SPOT", time.time(), "USD",
                            PortfolioSourceType.READ_ONLY_API_ACCOUNT_DATA,
                            total_market_value=Decimal("500"))
    view = UnifiedPortfolioView(generated_at=time.time(), snapshots=(npr, usd))
    d = view.to_public()
    assert set(d["by_currency"]) == {"NPR", "USD"}
    assert d["combined_valuation"] is None            # no FX → no combined sum
    view2 = UnifiedPortfolioView(generated_at=time.time(), snapshots=(npr, usd),
                                 fx=FXObservation("USDNPR", Decimal("133.5"), "sourced", time.time()))
    assert "combined_valuation_note" in view2.to_public()


# 16 — source attribution present
def test_source_types():
    for st in PortfolioSourceType:
        assert "PORTFOLIO" in st.value or "ACCOUNT" in st.value or "OBSERVED" in st.value


# 17 — no execution path in the finance package
def test_no_execution_path():
    import saathi.platform.finance.policy as p
    import saathi.platform.finance.session as se
    import saathi.platform.finance.portfolio as po
    import saathi.platform.finance.audit as au
    for m in (p, se, po, au):
        src = open(m.__file__).read()
        for banned in (".execute(", "place_order(", "create_order(", "submit_order(",
                       "cancel_order(", "withdraw(", "transfer(", "ExecutionGateway("):
            assert banned not in src, f"{banned} in {m.__file__}"


# 18 — prompt-injection: page text cannot grant an action (enforce ignores content)
def test_prompt_injection_defense():
    # a malicious "action" derived from page text is still just an action string → blocked
    for evil in ("BUY", "WITHDRAW", "SEND_CRYPTO", "CREATE_API_KEY", "IGNORE_PREVIOUS_INSTRUCTIONS"):
        assert enforce(Actor.AGENT_INPUT, evil, Provider.BINANCE)[0] is False


# 19 — interaction default modes per provider policy
def test_default_modes():
    assert POLICIES[Provider.NEPSE].default_interaction_mode == InteractionMode.AGENT_READ_ONLY
    assert POLICIES[Provider.BINANCE].default_interaction_mode == InteractionMode.OWNER_CONTROL
    assert POLICIES[Provider.TMS].default_interaction_mode == InteractionMode.OWNER_CONTROL


# 20 — no downloads/uploads by default; allowlist-only navigation
def test_navigation_download_policy():
    for prov, pol in POLICIES.items():
        assert pol.allowed_downloads is False and pol.allowed_uploads is False
        assert pol.navigation_policy == "ALLOWLIST_ONLY"
