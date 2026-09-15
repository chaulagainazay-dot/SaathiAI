"""M — BROWSER_AUTHENTICATED_FINANCIAL_PORTFOLIO_RUNTIME tests (credential-independent).

Fake dict-backed page reader; no real browser, no credentials. Proves owner/agent boundary
(Saathi Read gate), no-interaction observers/reader, allowlist + private-field redaction,
deterministic snapshot mapping (OWNER_AUTHENTICATED_BROWSER_OBSERVED), currency separation,
chat/voice, kill switch, provider isolation, no execution path, frozen-contract integrity.
"""
from __future__ import annotations

import time
from decimal import Decimal

from saathi.platform.finance.browser_portfolio import (
    build_snapshot, chat_answer, portfolio_view, voice_answer,
)
from saathi.platform.finance.browser_runtime import (
    AuthState, FinancialBrowserRuntimeManager, ObservationState, RuntimeState,
)
from saathi.platform.finance.observer import (
    ReadOnlyPageReader, TMSBrowserPortfolioObserver, BinanceBrowserPortfolioObserver, get_observer,
)
from saathi.platform.finance.policy import Provider
from saathi.platform.finance.portfolio import PortfolioSnapshot, PortfolioSourceType, UnifiedPortfolioView


class FakeReader:
    def __init__(self, rows, present=True):
        self._rows, self._present = rows, present
    def exists(self, sel): return self._present
    def count(self, sel): return len(self._rows)
    def text(self, sel): return None
    def rows(self, rsel, fields): return self._rows


TMS_ROWS = [{"symbol": "NABIL", "quantity": "100", "available": "100", "wacc": "500",
             "displayed_value": "55400", "name": "OWNER NAME", "boid": "12345"},
            {"symbol": "HDL", "quantity": "50", "available": "50", "wacc": "1100",
             "displayed_value": "60050"}]
BIN_ROWS = [{"asset": "BTC", "quantity": "0.5", "available": "0.5", "locked": "0"},
            {"asset": "USDT", "quantity": "1000", "available": "1000", "locked": "0"}]


# 1 — no display → DISPLAY_UNAVAILABLE; runtime carries no secrets
def test_open_no_display(monkeypatch):
    monkeypatch.delenv("SAATHI_FINANCE_HEADED", raising=False)
    monkeypatch.delenv("DISPLAY", raising=False)
    m = FinancialBrowserRuntimeManager()
    rt = m.open(Provider.TMS)
    assert rt.runtime_state == RuntimeState.DISPLAY_UNAVAILABLE
    d = rt.to_public()
    for bad in ("password", "otp", "cookie", "secret", "token", "storage"):
        assert not any(bad in k.lower() for k in d)
    assert not any(x in vars(rt) for x in ("password", "cookie", "secret", "storage_state"))


# 2 — Saathi Read gate: default OFF, needs owner auth, revocable
def test_saathi_read_gate():
    m = FinancialBrowserRuntimeManager()
    rt = m.open(Provider.BINANCE)
    assert rt.observation_state == ObservationState.SAATHI_READ_OFF
    assert m.read_allowed(rt.runtime_id) is False
    m.set_saathi_read(rt.runtime_id, True)               # before owner auth → refused
    assert m.read_allowed(rt.runtime_id) is False
    m.mark_owner_authenticated(rt.runtime_id)
    m.set_saathi_read(rt.runtime_id, True)
    assert m.read_allowed(rt.runtime_id) is True
    m.disable_saathi_read(rt.runtime_id)                 # kill switch
    assert m.read_allowed(rt.runtime_id) is False


# 3 — close revokes read + clears
def test_close():
    m = FinancialBrowserRuntimeManager()
    rt = m.open(Provider.TMS)
    m.mark_owner_authenticated(rt.runtime_id); m.set_saathi_read(rt.runtime_id, True)
    m.close(rt.runtime_id)
    assert m.get(rt.runtime_id).runtime_state == RuntimeState.CLOSED
    assert m.read_allowed(rt.runtime_id) is False


# 4 — provider isolation
def test_isolation():
    m = FinancialBrowserRuntimeManager()
    a = m.open(Provider.TMS); b = m.open(Provider.BINANCE)
    m.mark_owner_authenticated(b.runtime_id); m.set_saathi_read(b.runtime_id, True)
    m.close(a.runtime_id)
    assert m.get(a.runtime_id).runtime_state == RuntimeState.CLOSED
    assert m.read_allowed(b.runtime_id) is True


# 5 — observers + reader have NO interaction methods
def test_no_interaction():
    for obj in (TMSBrowserPortfolioObserver(), BinanceBrowserPortfolioObserver(),
                ReadOnlyPageReader(None)):
        for banned in ("click", "type", "goto", "fill", "press", "submit", "navigate",
                       "download", "upload", "evaluate", "select_option"):
            assert not hasattr(obj, banned), (obj, banned)


# 6 — allowlist + private-field drop + selectors provisional
def test_allowlist_redaction():
    obs = get_observer("TMS")
    rows, lims = obs.observe_portfolio(FakeReader(TMS_ROWS))
    assert rows and all("name" not in r and "boid" not in r for r in rows)     # private dropped
    assert all(set(r).issubset(set(obs.ALLOWED_FIELDS)) for r in rows)
    assert any("PROVISIONAL_UNVERIFIED" in l for l in lims)


# 7 — auth detection deterministic; never reads credentials
def test_auth_detection():
    obs = get_observer("TMS")
    assert obs.authentication_state(FakeReader(TMS_ROWS, present=True)) == AuthState.OWNER_AUTHENTICATED
    assert obs.authentication_state(FakeReader(TMS_ROWS, present=False)) == AuthState.UNKNOWN


# 8 — snapshot mapping (TMS EQUITY/NPR; source OWNER_AUTHENTICATED_BROWSER_OBSERVED)
def test_snapshot_tms():
    obs = get_observer("TMS"); rows, _ = obs.observe_portfolio(FakeReader(TMS_ROWS))
    snap = build_snapshot("TMS", rows)
    assert snap.source_type == PortfolioSourceType.OWNER_AUTHENTICATED_BROWSER_OBSERVED
    assert snap.data_class == "OWNER_AUTHENTICATED_BROWSER_OBSERVATION" and snap.currency == "NPR"
    nabil = next(p for p in snap.positions if p.symbol == "NABIL")
    assert nabil.asset_type == "EQUITY" and str(nabil.quantity) == "100"
    assert str(nabil.average_cost) == "500" and str(nabil.market_value) == "55400"
    assert nabil.current_price is None and nabil.cost_basis is None    # not fabricated


# 9 — displayed value marked browser-displayed, not canonical
def test_displayed_value_source():
    obs = get_observer("TMS"); rows, _ = obs.observe_portfolio(FakeReader(TMS_ROWS))
    snap = build_snapshot("TMS", rows)
    p = snap.positions[0]
    assert p.current_price_source == "BROWSER_DISPLAYED"
    assert any("not canonical" in l for l in snap.limitations)


# 10 — Binance mapping (CRYPTO/STABLECOIN/USDT)
def test_snapshot_binance():
    obs = get_observer("BINANCE"); rows, _ = obs.observe_portfolio(FakeReader(BIN_ROWS))
    snap = build_snapshot("BINANCE", rows)
    assert snap.currency == "USDT"
    types = {p.symbol: p.asset_type for p in snap.positions}
    assert types["BTC"] == "CRYPTO" and types["USDT"] == "STABLECOIN"


# 11 — view: PNL/cost basis unavailable
def test_view():
    rows, _ = get_observer("TMS").observe_portfolio(FakeReader(TMS_ROWS))
    v = portfolio_view(build_snapshot("TMS", rows))
    assert v["pnl"] == "PNL_UNAVAILABLE" and v["cost_basis"] == "COST_BASIS_UNAVAILABLE"
    assert v["largest_position"]["symbol"] in ("HDL", "NABIL")


# 12 — chat / voice
def test_chat_voice():
    rows, _ = get_observer("TMS").observe_portfolio(FakeReader(TMS_ROWS))
    v = portfolio_view(build_snapshot("TMS", rows))
    assert "NABIL" in chat_answer("how many NABIL do I own?", view=v)["answer"]
    assert "PNL_UNAVAILABLE" in chat_answer("my profit?", view=v)["answer"]
    assert chat_answer("show portfolio", view=None)["state"] == "OWNER_FINANCIAL_LOGIN_REQUIRED"
    assert "NABIL" in voice_answer("mero NABIL kati", view=v)


# 13 — UnifiedPortfolioView currency separation
def test_currency_separation():
    tms = build_snapshot("TMS", get_observer("TMS").observe_portfolio(FakeReader(TMS_ROWS))[0])
    binance = build_snapshot("BINANCE", get_observer("BINANCE").observe_portfolio(FakeReader(BIN_ROWS))[0])
    view = UnifiedPortfolioView(generated_at=time.time(), snapshots=(tms, binance)).to_public()
    assert set(view["by_currency"]) == {"NPR", "USDT"} and view["combined_valuation"] is None


# 14 — no execution path in the runtime modules
def test_no_execution_path():
    import saathi.platform.finance.browser_runtime as m1
    import saathi.platform.finance.observer as m2
    import saathi.platform.finance.browser_portfolio as m3
    for m in (m1, m2, m3):
        src = open(m.__file__).read()
        for banned in ("place_order", "def buy", "def sell", "def withdraw", "def transfer",
                       "ExecutionGateway(", ".execute("):
            assert banned not in src, (m.__file__, banned)


# 15 — Binance API adapter kept intact + not required
def test_binance_api_adapter_intact(monkeypatch):
    monkeypatch.delenv("BINANCE_API_KEY", raising=False)
    import saathi.platform.finance.binance_account as ba
    assert hasattr(ba, "BinanceReadOnlyAccountAdapter")     # deferred, not deleted


# 16 — private/OTP field never surfaces even if present in a row
def test_private_never_surfaces():
    rows, _ = get_observer("TMS").observe_portfolio(
        FakeReader([{"symbol": "NABIL", "quantity": "100", "password": "x", "otp": "123456"}]))
    assert rows and "password" not in rows[0] and "otp" not in rows[0]


# 17 — prohibited regions declared per observer
def test_prohibited_regions():
    assert "withdraw" in BinanceBrowserPortfolioObserver.PROHIBITED_REGIONS
    assert any(x in TMSBrowserPortfolioObserver.PROHIBITED_REGIONS for x in ("buy", "sell", "order"))


# 17b — read_portfolio orchestration: gating + OK + empty/schema + enrichment
def test_read_portfolio_orchestration(monkeypatch):
    from saathi.platform.finance import browser_portfolio as bp
    m = FinancialBrowserRuntimeManager()
    rt = m.open(Provider.TMS)
    # not owner-authenticated yet
    assert bp.read_portfolio(rt.runtime_id, manager=m, reader=FakeReader(TMS_ROWS))["state"] == "OWNER_TMS_LOGIN_REQUIRED"
    m.mark_owner_authenticated(rt.runtime_id)
    # owner-authed but Saathi Read OFF
    assert bp.read_portfolio(rt.runtime_id, manager=m, reader=FakeReader(TMS_ROWS))["state"] == "SAATHI_READ_OFF"
    m.set_saathi_read(rt.runtime_id, True)
    # OK read (enrich off to avoid live-service dependency)
    out = bp.read_portfolio(rt.runtime_id, manager=m, reader=FakeReader(TMS_ROWS), enrich=False)
    assert out["available"] and out["state"] == "OK"
    syms = {p["symbol"] for p in out["view"]["positions"]}
    assert "NABIL" in syms and out["view"]["selectors_verified"] is False
    # empty rows → schema-changed-or-unverified (not silent empty)
    empty = bp.read_portfolio(rt.runtime_id, manager=m, reader=FakeReader([]), enrich=False)
    assert empty["available"] is False and "SCHEMA_CHANGED" in empty["state"]
    # official enrichment (authority for current price) + reconciliation
    monkeypatch.setattr(bp, "_official_ltp", lambda s: Decimal("560") if s == "NABIL" else None)
    enr = bp.read_portfolio(rt.runtime_id, manager=m, reader=FakeReader(TMS_ROWS), enrich=True)
    nabil = next(p for p in enr["view"]["positions"] if p["symbol"] == "NABIL")
    assert nabil["current_price"] == "560" and nabil["current_price_source"] == "OFFICIAL_PAGE_OBSERVED"
    rec = {r["symbol"]: r["verdict"] for r in enr["view"]["reconciliation"]}
    assert rec["NABIL"] in ("CONFIRMED", "SOURCE_DISAGREEMENT")


# 18 — read blocked before owner authentication (manager gate)
def test_read_requires_owner_auth():
    m = FinancialBrowserRuntimeManager()
    rt = m.open(Provider.BINANCE)
    m.set_saathi_read(rt.runtime_id, True)   # ignored (not authed)
    assert m.get(rt.runtime_id).observation_state == ObservationState.SAATHI_READ_OFF
