"""M304–M311 Read-Only Market Observation tests.

VALIDATION — NOT TRADING. No broker login, OAuth, credentials, orders, accounts.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from saathi.platform.tg.market_observation.models import (
    ACCOUNT_ACCESS_AUTHORIZED,
    API_KEYS_ACCEPTED,
    BROKER_CONNECTIVITY_AUTHORIZED,
    CREDENTIAL_STORAGE_AUTHORIZED,
    LIVE_TRADING_AUTHORIZED,
    OAUTH_AUTHORIZED,
    ORDER_EXECUTION_AUTHORIZED,
    TERMINAL_VERDICT,
)
from saathi.platform.tg.market_observation.service import (
    MarketObservationService,
    reset_market_observation_for_tests,
)


@pytest.fixture()
def svc(tmp_path: Path):
    return reset_market_observation_for_tests(db_path=tmp_path / "mo_test.db")


def test_authority_locks():
    assert LIVE_TRADING_AUTHORIZED is False
    assert BROKER_CONNECTIVITY_AUTHORIZED is False
    assert ORDER_EXECUTION_AUTHORIZED is False
    assert ACCOUNT_ACCESS_AUTHORIZED is False
    assert CREDENTIAL_STORAGE_AUTHORIZED is False
    assert OAUTH_AUTHORIZED is False
    assert API_KEYS_ACCEPTED is False


def test_symbols_and_quotes(svc: MarketObservationService):
    syms = svc.list_symbols()
    assert syms["count"] >= 5
    q = svc.get_quote("SPY")
    assert q["ok"]
    assert q["quote"]["freshness"] == "FROZEN"
    assert q["quote"].get("live_stream") is False or "bid" in q["quote"]


def test_snapshot_and_history(svc: MarketObservationService):
    snap = svc.market_snapshot(label="t")
    assert snap["ok"]
    assert snap["authenticated"] is False
    hist = svc.historical_refresh("AAPL", n=20)
    assert hist["bar_count"] == 20
    assert hist["authenticated_live"] is False


def test_exchange_status_ca_benchmarks(svc: MarketObservationService):
    ex = svc.list_exchange_status()
    assert ex["count"] >= 1
    ca = svc.list_corporate_actions("AAPL")
    assert ca["ok"]
    bm = svc.update_benchmarks()
    assert bm["count"] >= 1
    assert bm["authenticated_live"] is False


def test_all_refusals(svc: MarketObservationService):
    assert svc.refuse_broker_login()["refused"] is True
    assert svc.refuse_oauth()["refused"] is True
    assert svc.refuse_credentials("k")["refused"] is True
    assert svc.refuse_credentials("k").get("stored") is False
    assert svc.refuse_order()["refused"] is True
    assert svc.refuse_account_access()["refused"] is True
    assert svc.refuse_portfolio_access()["refused"] is True
    assert svc.refuse_balance_access()["refused"] is True
    assert svc.refuse_canary()["refused"] is True
    assert svc.refuse_live_trading()["refused"] is True
    assert svc.refuse_authenticated_live_feed()["refused"] is True


def test_credential_sql_blocked(svc: MarketObservationService):
    with pytest.raises(ValueError):
        svc.store.execute("INSERT INTO mo_meta(key, value, updated_at) VALUES('api_key','x',0)")


def test_bootstrap_and_certify(svc: MarketObservationService):
    pipe = svc.bootstrap_demo_pipeline()
    assert pipe["ok"] is True
    assert pipe["authenticated_live"] is False
    cert = svc.certify()
    assert cert["ok"] is True
    assert cert["verdict"] == TERMINAL_VERDICT
    assert cert["purpose"] == "validation_not_trading"
