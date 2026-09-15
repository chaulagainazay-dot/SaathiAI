"""M — BINANCE_READONLY_ACCOUNT_ADAPTER Gate A tests (Phase 37).

Credential-independent: mock transports, no network, no secrets. Proves permission
assessment (default-deny), endpoint allowlist (order/withdraw/transfer/margin/futures
blocked), no generic signed request, no execution path, PortfolioSnapshot mapping,
zero-balance/dust/locked/stablecoin handling, public price enrichment, missing-quote,
valuation/allocation, P/L unavailable, currency separation, chat/voice, states, cache,
kill/disconnect, audit, secret/signature non-exposure.
"""
from __future__ import annotations

import time
from decimal import Decimal

import pytest

from saathi.platform.finance import audit
from saathi.platform.finance.binance_account import (
    BinanceReadOnlyAccountAdapter, EndpointBlocked, PermissionAssessment,
    SIGNED_READ_ALLOWLIST, assess_permissions, is_safe,
)
from saathi.platform.finance.crypto_portfolio import (
    BinanceConnection, ConnectionState, build_snapshot, chat_answer, crypto_view, voice_answer,
)
from saathi.platform.finance.portfolio import (
    PortfolioSnapshot, PortfolioSourceType, UnifiedPortfolioView,
)

RESTR_SAFE = {"enableReading": True, "enableWithdrawals": False, "enableInternalTransfer": False,
              "permitsUniversalTransfer": False, "enableFutures": False, "enableMargin": False,
              "enableSpotAndMarginTrading": False}
ACCT = {"canTrade": False, "canWithdraw": False, "balances": [
    {"asset": "BTC", "free": "0.5", "locked": "0.0"},
    {"asset": "USDT", "free": "1000", "locked": "0"},
    {"asset": "ETH", "free": "2", "locked": "1"},
    {"asset": "USDC", "free": "50", "locked": "0"},
    {"asset": "ZZZ", "free": "5", "locked": "0"},        # no price → PRICE_UNAVAILABLE
    {"asset": "XRP", "free": "0", "locked": "0"}]}        # zero → filtered
PRICES = {"BTCUSDT": "60000", "ETHUSDT": "3000", "USDCUSDT": "0.9998"}


def _adapter(restr=RESTR_SAFE, acct=ACCT, counter=None):
    def signed(method, path, params, *, signed=True, api_key=None, secret=None):
        if counter is not None:
            counter["signed"] = counter.get("signed", 0) + 1
        return restr if path.endswith("apiRestrictions") else acct

    def public(path, params):
        if path.endswith("/ticker/price"):
            return {"symbol": params.get("symbol"), "price": PRICES.get(params.get("symbol"), "0")}
        if path.endswith("/time"):
            return {"serverTime": int(time.time() * 1000) + 3}
        return {}
    return BinanceReadOnlyAccountAdapter(transport=signed, public_transport=public)


# 1 — safe permission
def test_permission_safe():
    assert _adapter().assess() == PermissionAssessment.READ_ONLY_CONFIRMED
    assert is_safe(PermissionAssessment.READ_ONLY_CONFIRMED)


# 2 — unsafe permission rejection (each flag)
def test_permission_unsafe():
    for flag, exp in [("enableWithdrawals", "UNSAFE_WITHDRAW_PERMISSION"),
                      ("enableSpotAndMarginTrading", "UNSAFE_TRADING_PERMISSION"),
                      ("enableMargin", "UNSAFE_MARGIN_PERMISSION"),
                      ("enableFutures", "UNSAFE_FUTURES_PERMISSION"),
                      ("permitsUniversalTransfer", "UNSAFE_TRANSFER_PERMISSION")]:
        r = dict(RESTR_SAFE); r[flag] = True
        assert assess_permissions(r).value == exp
    assert assess_permissions(None) == PermissionAssessment.CREDENTIAL_INVALID
    assert assess_permissions({"enableReading": False}) == PermissionAssessment.CREDENTIAL_INVALID
    assert assess_permissions({"enableReading": True}) == PermissionAssessment.PERMISSION_UNKNOWN


# 3 — account canTrade/canWithdraw cross-check
def test_account_crosscheck():
    acct = dict(ACCT); acct["canTrade"] = True
    assert assess_permissions(RESTR_SAFE, acct) == PermissionAssessment.UNSAFE_TRADING_PERMISSION


# 4 — endpoint allowlist: only 2 signed endpoints; order/withdraw/etc blocked
def test_endpoint_allowlist():
    assert SIGNED_READ_ALLOWLIST == {"/api/v3/account", "/sapi/v1/account/apiRestrictions"}
    ad = _adapter()
    for blocked in ("/api/v3/order", "/sapi/v1/capital/withdraw/apply", "/sapi/v1/asset/transfer",
                    "/sapi/v1/margin/order", "/fapi/v1/order", "/sapi/v1/margin/loan"):
        with pytest.raises(EndpointBlocked):
            ad._signed_get(blocked)


# 5 — no generic signed request / no execution methods on the adapter
def test_no_execution_methods():
    ad = _adapter()
    for banned in ("place_order", "cancel_order", "withdraw", "transfer", "borrow", "repay",
                   "set_leverage", "enable_margin", "enable_futures", "post", "signed_request",
                   "request", "order"):
        assert not hasattr(ad, banned), banned


# 6 — no execution path / no POST-PUT-DELETE in module source
def test_no_execution_source():
    import saathi.platform.finance.binance_account as m
    src = open(m.__file__).read()
    for banned in ("place_order", "def withdraw", "def transfer", "ExecutionGateway(",
                   '"POST"', "'POST'", '"DELETE"', '"PUT"', ".execute("):
        assert banned not in src, banned


# 7 — snapshot mapping into frozen contract
def test_snapshot_mapping():
    snap, st = build_snapshot(_adapter())
    assert st == ConnectionState.READ_ONLY_CONNECTED
    assert snap.provider == "BINANCE" and snap.account_type == "CRYPTO"
    assert snap.source_type == PortfolioSourceType.READ_ONLY_API_ACCOUNT_DATA
    assert snap.data_class == "READ_ONLY_ACCOUNT_OBSERVATION"


# 8 — zero-balance filtered; locked preserved; stablecoin classified
def test_balances():
    snap, _ = build_snapshot(_adapter())
    syms = {p.symbol for p in snap.positions}
    assert "XRP" not in syms and "BTC" in syms and "ZZZ" in syms   # ZZZ nonzero but unpriced
    eth = next(p for p in snap.positions if p.symbol == "ETH")
    assert str(eth.locked_quantity) == "1" and str(eth.quantity) == "3"
    usdt = next(p for p in snap.positions if p.symbol == "USDT")
    assert usdt.asset_type == "STABLECOIN"


# 9 — public price enrichment + valuation + missing quote
def test_pricing():
    snap, _ = build_snapshot(_adapter())
    btc = next(p for p in snap.positions if p.symbol == "BTC")
    assert btc.current_price == Decimal("60000") and btc.market_value == Decimal("30000.0")
    assert btc.current_price_source == "BINANCE_PUBLIC"
    zzz = next(p for p in snap.positions if p.symbol == "ZZZ")
    assert zzz.current_price is None and zzz.market_value is None
    assert any("PRICE_UNAVAILABLE" in l for l in snap.limitations)


# 10 — stablecoin NOT assumed 1:1 (USDC priced via USDCUSDT)
def test_stablecoin_not_hardcoded():
    snap, _ = build_snapshot(_adapter())
    usdc = next(p for p in snap.positions if p.symbol == "USDC")
    assert usdc.current_price == Decimal("0.9998")     # real quote, not 1


# 11 — allocation + P/L unavailable
def test_view():
    snap, _ = build_snapshot(_adapter())
    v = crypto_view(snap)
    assert v["largest_position"]["asset"] == "BTC"
    assert v["pnl"] == "PNL_UNAVAILABLE" and v["cost_basis"] == "COST_BASIS_UNAVAILABLE"
    # BTC 30000 of total (30000+1000+9000+~50) ≈ 75%
    assert Decimal(v["largest_position"]["allocation_pct"]) > Decimal("70")


# 12 — cost basis / pnl never fabricated
def test_no_fabricated_pnl():
    snap, _ = build_snapshot(_adapter())
    for p in snap.positions:
        assert p.average_cost is None and p.cost_basis is None
        assert p.unrealized_pnl is None and p.realized_pnl is None


# 13 — permission-unsafe blocks the read
def test_unsafe_blocks_read():
    r = dict(RESTR_SAFE); r["enableWithdrawals"] = True
    snap, st = build_snapshot(_adapter(restr=r))
    assert snap is None and st == ConnectionState.PERMISSION_UNSAFE


# 14 — UnifiedPortfolioView currency separation (no NPR+USDT sum)
def test_currency_separation():
    binance, _ = build_snapshot(_adapter())
    npr = PortfolioSnapshot("n", "owner", "TMS", "NEPSE_DEMAT", time.time(), "NPR",
                            PortfolioSourceType.OWNER_IMPORTED_PORTFOLIO,
                            total_market_value=Decimal("100000"))
    view = UnifiedPortfolioView(generated_at=time.time(), snapshots=(binance, npr)).to_public()
    assert set(view["by_currency"]) == {"USDT", "NPR"} and view["combined_valuation"] is None


# 15 — chat / voice
def test_chat_voice():
    snap, _ = build_snapshot(_adapter())
    v = crypto_view(snap)
    assert "BTC" in chat_answer("how much BTC do I have?", view=v)["answer"]
    assert "%" in chat_answer("what percentage is BTC?", view=v)["answer"]
    assert "stablecoin" in chat_answer("how much in stablecoins?", view=v)["answer"].lower()
    assert "PNL_UNAVAILABLE" in chat_answer("what is my profit?", view=v)["answer"]
    assert "OWNER_ACTION_REQUIRED" == chat_answer("show portfolio", view=None)["state"]
    assert "BTC" in voice_answer("bitcoin ma kati", view=v)


# 16 — cache: one read serves repeated snapshot() within TTL
def test_cache():
    counter = {"signed": 0}
    conn = BinanceConnection(adapter=_adapter(counter=counter))
    conn.snapshot(now=1000.0)
    n1 = counter["signed"]
    conn.snapshot(now=1010.0)
    assert counter["signed"] == n1              # cached, no new signed reads
    conn.snapshot(force=True, now=1020.0)
    assert counter["signed"] > n1


# 17 — kill switch + disconnect
def test_kill_disconnect():
    conn = BinanceConnection(adapter=_adapter())
    conn.snapshot()
    conn.kill()
    assert conn.state == ConnectionState.NOT_CONNECTED and conn.adapter is None
    conn2 = BinanceConnection(adapter=_adapter())
    conn2.snapshot(); conn2.disconnect()
    assert conn2.state == ConnectionState.NOT_CONNECTED and conn2._snap is None


# 18 — clock skew
def test_clock_skew():
    assert isinstance(_adapter().server_time_skew_ms(), int)


# 19 — audit records read, no secrets
def test_audit_no_secrets():
    audit.clear()
    build_snapshot(_adapter())
    t = audit.tail(10)
    assert any(r["capability"] == "BINANCE_ACCOUNT_READ" and r["result"] == "OK" for r in t)
    blob = " ".join(r["detail"] for r in t)
    assert "secret" not in blob.lower() and "signature" not in blob.lower()


# 20 — no owner credentials configured → OWNER_ACTION_REQUIRED (never asks in chat)
def test_owner_action_required(monkeypatch):
    monkeypatch.delenv("BINANCE_API_KEY", raising=False)
    monkeypatch.delenv("BINANCE_API_SECRET", raising=False)
    import saathi.platform.finance.crypto_portfolio as cp
    assert cp._configure_from_env() is None
