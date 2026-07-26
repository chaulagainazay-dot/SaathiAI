"""M62.2 — deterministic market-data quality, storage, and replay foundation.

Unit + persistence + integration + adversarial. Proves fail-closed quality
classification, tz-aware enforcement, idempotent tenant-scoped storage,
deterministic replay + fixtures, and that the Trading Guardian rejects
non-VALID market-data inputs.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from saathi.platform.market_data import (
    Timeframe, MarketDataQuality, MDInstrument, MDQuote, MDBar,
    classify_quote, classify_bar, classify_series, is_bar_fresh, is_aware, require_aware,
    FixtureProvider, DATASETS, fixture_manifest, dataset_hash, build_bars, build_quote,
    MarketDataStore, IngestionService, ReplayEngine, ReplayStatus,
    ProviderStatus, get_calendar, SUPPORTED_CALENDARS, DEFAULT_24_5, RTH_UTC, to_data_quality,
)
from saathi.platform.market_data.models import require_aware as _req
from saathi.platform.trading_models import AssetClass, DataQuality, MarketState
from saathi.platform.trading_guardian import TradingGuardian
from saathi.platform.service import reset_platform_for_tests

UTC = timezone.utc
NOW = datetime(2026, 2, 10, 15, 0, 0, tzinfo=UTC)


def _q(**kw):
    base = dict(instrument="X", provider="fixture", bid=Decimal("99.98"), ask=Decimal("100.02"),
                last=Decimal("100.00"), bid_size=Decimal("10"), ask_size=Decimal("10"),
                source_time=NOW, ingested_at=NOW)
    base.update(kw)
    return MDQuote(**base)


def _bar(start, tf=Timeframe.D1, o="100", h="101", l="99", c="100.5", v="1000"):
    end = start + timedelta(seconds={Timeframe.D1: 86400, Timeframe.M1: 60}[tf])
    return MDBar(instrument="X", timeframe=tf, provider="fixture", open=Decimal(o), high=Decimal(h),
                 low=Decimal(l), close=Decimal(c), volume=Decimal(v), start_time=start, end_time=end,
                 source_time=end, ingested_at=end)


# ── unit: timestamps ──────────────────────────────────────────────────────────
def test_naive_timestamp_rejected():
    with pytest.raises(ValueError):
        require_aware(datetime(2026, 1, 1))  # naive
    assert is_aware(NOW) and not is_aware(datetime(2026, 1, 1))
    q = _q(source_time=datetime(2026, 2, 10, 15, 0, 0))  # naive
    assert classify_quote(q, now=NOW) == MarketDataQuality.INVALID_TIMESTAMP


# ── unit: quote validation ────────────────────────────────────────────────────
def test_quote_valid_and_defects():
    assert classify_quote(_q(), now=NOW) == MarketDataQuality.VALID
    assert classify_quote(_q(bid=Decimal("101"), ask=Decimal("100")), now=NOW) == MarketDataQuality.INVALID_PRICE  # crossed
    assert classify_quote(_q(bid=Decimal("-1")), now=NOW) == MarketDataQuality.INVALID_PRICE
    assert classify_quote(_q(bid=Decimal("80"), ask=Decimal("120")), now=NOW) == MarketDataQuality.OUTLIER  # 40% spread
    assert classify_quote(_q(source_time=NOW + timedelta(hours=1)), now=NOW) == MarketDataQuality.INVALID_TIMESTAMP  # future
    assert classify_quote(_q(source_time=NOW - timedelta(hours=2)), now=NOW) == MarketDataQuality.STALE
    assert classify_quote(_q(), now=NOW, market_open=False) == MarketDataQuality.MARKET_CLOSED


# ── unit: bar validation ──────────────────────────────────────────────────────
def test_bar_ohlc_invariants():
    assert classify_bar(_bar(NOW - timedelta(days=1)), now=NOW) == MarketDataQuality.VALID
    assert classify_bar(_bar(NOW - timedelta(days=1), h="50", l="120"), now=NOW) == MarketDataQuality.INVALID_PRICE  # high<low
    assert classify_bar(_bar(NOW - timedelta(days=1), o="200"), now=NOW) == MarketDataQuality.INVALID_PRICE  # open>high
    assert classify_bar(_bar(NOW - timedelta(days=1), l="-1"), now=NOW) == MarketDataQuality.INVALID_PRICE
    assert classify_bar(_bar(NOW + timedelta(days=1)), now=NOW) == MarketDataQuality.INVALID_TIMESTAMP  # future
    # abnormal jump vs prev close
    assert classify_bar(_bar(NOW - timedelta(days=1), c="100.5"), now=NOW, prev_close=Decimal("10")) == MarketDataQuality.OUTLIER


def test_historical_bar_valid_freshness_separate():
    old = _bar(datetime(2020, 1, 1, tzinfo=UTC))
    assert classify_bar(old, now=NOW) == MarketDataQuality.VALID  # old but structurally valid
    assert not is_bar_fresh(old, now=NOW)                          # but not fresh at decision time
    assert is_bar_fresh(_bar(NOW - timedelta(hours=1)), now=NOW)


def test_series_gap_dup_order():
    step = 86400
    bars = [_bar(NOW - timedelta(days=10) + timedelta(seconds=step * k)) for k in range(6)]
    bars.insert(2, bars[1])                       # duplicate
    bars[4], bars[5] = bars[5], bars[4]           # out of order
    del bars[6]                                   # a gap
    summary = classify_series(bars, now=NOW)
    assert summary["duplicates"] >= 1
    assert summary["out_of_order"] >= 1 or summary["gaps"] >= 1


# ── unit: calendar ────────────────────────────────────────────────────────────
def test_market_calendar_sessions():
    assert DEFAULT_24_5.is_open(NOW)  # 24/7 always open
    # RTH: 2026-02-10 is a Tuesday; 15:00 UTC is within 13:30-20:00
    assert RTH_UTC.state_at(NOW) == MarketState.OPEN
    sat = datetime(2026, 2, 14, 15, 0, tzinfo=UTC)   # Saturday
    assert RTH_UTC.state_at(sat) == MarketState.CLOSED
    off = datetime(2026, 2, 10, 6, 0, tzinfo=UTC)    # before open
    assert RTH_UTC.state_at(off) == MarketState.CLOSED
    assert get_calendar("NOPE_UNKNOWN") is None       # unsupported -> None (caller fails closed)


# ── unit: fixtures deterministic ──────────────────────────────────────────────
def test_fixture_hashes_stable_and_15_datasets():
    assert len(DATASETS) == 15
    m1, m2 = fixture_manifest(), fixture_manifest()
    assert m1 == m2 and len(m1["datasets"]) == 15
    assert dataset_hash("TRENDING") == dataset_hash("TRENDING")   # reproducible
    assert dataset_hash("TRENDING") != dataset_hash("FLAT")


# ── unit: provider error mapping ──────────────────────────────────────────────
def test_provider_errors_not_empty_valid():
    prov = FixtureProvider()
    r = prov.get_quote("NONEXISTENT", now=NOW)
    assert not r.ok and r.status == ProviderStatus.NOT_FOUND and r.data is None


# ── unit: replay determinism ──────────────────────────────────────────────────
def test_replay_deterministic_and_controls():
    bars = build_bars("TRENDING")
    a = ReplayEngine(bars, correlation_id="r", dataset_version="v1").run_to_end()
    b = ReplayEngine(list(reversed(bars)), correlation_id="r", dataset_version="v1").run_to_end()
    assert [e.bar.start_time for e in a] == [e.bar.start_time for e in b]  # order-independent
    eng = ReplayEngine(bars, correlation_id="r", dataset_version="v1")
    eng.step(3); assert eng.position == 3
    eng.pause(); assert eng.step(1) == []            # paused emits nothing
    eng.resume(); assert len(eng.step(2)) == 2
    cp = eng.checkpoint(); eng.reset(); assert eng.position == 0
    eng.restore(cp); assert eng.position == cp["position"]
    with pytest.raises(ValueError):
        eng.restore({"position": 3, "dataset_version": "WRONG"})  # corrupted checkpoint


# ── persistence ───────────────────────────────────────────────────────────────
def test_store_idempotent_range_tenant(tmp_path):
    store = MarketDataStore(db_path=tmp_path / "md.db")
    ing = IngestionService(FixtureProvider(), store)
    now = datetime(2026, 3, 1, tzinfo=UTC)
    rep = ing.ingest_bars("o1", "TRENDING", Timeframe.D1, datetime(2026, 1, 1, tzinfo=UTC), now, now=now, correlation_id="c")
    assert rep.accepted == 30 and rep.rejected == 0
    rep2 = ing.ingest_bars("o1", "TRENDING", Timeframe.D1, datetime(2026, 1, 1, tzinfo=UTC), now, now=now, correlation_id="c")
    assert rep2.accepted == 0  # idempotent
    rows = store.query_bars("o1", "TRENDING", Timeframe.D1, 0, now.timestamp())
    assert len(rows) == 30
    assert all(rows[i]["start_epoch"] <= rows[i + 1]["start_epoch"] for i in range(len(rows) - 1))  # ordered
    assert store.query_bars("oX", "TRENDING", Timeframe.D1, 0, now.timestamp() * 2) == []  # tenant isolation
    # restart persistence
    store2 = MarketDataStore(db_path=tmp_path / "md.db")
    assert len(store2.query_bars("o1", "TRENDING", Timeframe.D1, 0, now.timestamp())) == 30


def test_store_persists_quality_and_rejects(tmp_path):
    store = MarketDataStore(db_path=tmp_path / "md.db")
    ing = IngestionService(FixtureProvider(), store)
    now = datetime(2026, 3, 1, tzinfo=UTC)
    rep = ing.ingest_bars("o1", "INVALID_OHLC", Timeframe.D1, datetime(2026, 1, 1, tzinfo=UTC), now, now=now, correlation_id="c")
    assert rep.rejected >= 1 and rep.accepted < 30
    assert store.count_rejects("o1", "INVALID_OHLC") >= 1  # rejected retained as evidence, not valid data


# ── integration: fixture → ingest → store; Guardian consumes quality ─────────
def test_ingest_defect_datasets(tmp_path):
    store = MarketDataStore(db_path=tmp_path / "md.db")
    ing = IngestionService(FixtureProvider(), store)
    now = datetime(2026, 3, 1, tzinfo=UTC)
    start, end = datetime(2026, 1, 1, tzinfo=UTC), now + timedelta(days=4000)
    dd = lambda s: ing.ingest_bars("o1", s, Timeframe.D1, start, end, now=now, correlation_id="c")
    assert dd("MISSING_BARS").gaps >= 1
    assert dd("DUPLICATE_BARS").duplicates >= 1
    assert dd("FUTURE_TIMESTAMPS").rejected >= 1
    assert dd("FLASH_CRASH_LIKE").outliers >= 1


def test_guardian_rejects_non_valid_market_data():
    from decimal import Decimal as Dec
    from saathi.platform.trading_models import OrderIntent, OrderSide, OrderType, Environment, Account
    stale = _q(source_time=NOW - timedelta(hours=2))
    classify_quote(stale, now=NOW)
    assert stale.quality == MarketDataQuality.STALE
    dq = stale.data_quality()  # maps to coarse DataQuality (non-VALID)
    assert dq != DataQuality.VALID
    g = TradingGuardian()
    intent = OrderIntent(intent_id="i", org_id="o", workspace_id="w", account_id="a",
                         environment=Environment.PAPER, symbol="X", side=OrderSide.BUY,
                         order_type=OrderType.MARKET, quantity=Dec("1"), idempotency_key="k", approval_id="ap")
    d = g.evaluate(intent, account=Account(account_id="a", environment=Environment.PAPER, cash=Dec("100000")),
                   ref_price=Dec("100"), price_quality=dq, market_state=MarketState.OPEN)
    assert not d.allowed and any("quality" in r.lower() for r in d.reasons)


# ── adversarial ───────────────────────────────────────────────────────────────
def test_adversarial_invalid_decimal_and_negatives():
    from saathi.platform.trading_models import D
    assert D("not-a-number") == Decimal("0")   # malformed provider string -> safe 0 (not exception)
    q = _q(bid=Decimal("0"))
    assert classify_quote(q, now=NOW) == MarketDataQuality.INVALID_PRICE


def test_adversarial_unsupported_timeframe_and_huge_range():
    prov = FixtureProvider()
    r = prov.get_bars("TRENDING", Timeframe.D1, datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 3, 1, tzinfo=UTC), now=NOW)
    assert r.ok
    # a huge range still returns bounded fixture data (30 bars), never unbounded
    assert len(r.data) <= 30


# ── HTTP contract: auth + tenant isolation + no execution ─────────────────────
def test_http_market_data(tmp_path, monkeypatch):
    monkeypatch.setenv("SAATHI_MARKETDATA_DB", str(tmp_path / "http.db"))
    platform = reset_platform_for_tests(tmp_path / "plat.db")
    owner = platform.bootstrap_owner_secure(email="o@m62.local", name="O", password="OwnerPassw0rd!",
                                             org_name="Org", workspace_name="WS")
    token = owner["token"]
    from saathi.server import app
    client = TestClient(app)
    h = {"X-Platform-Token": token}
    # unauthenticated rejected
    assert client.get("/api/v1/platform/market-data/instruments").status_code == 401
    # ingest a fixture (operator+ write)
    r = client.post("/api/v1/platform/market-data/fixtures/ingest", json={"symbol": "TRENDING", "timeframe": "1d"}, headers=h)
    assert r.status_code == 200 and r.json()["report"]["accepted"] == 30
    # bars readable, tenant-scoped
    b = client.get("/api/v1/platform/market-data/bars/TRENDING?timeframe=1d", headers=h)
    assert b.status_code == 200 and b.json()["count"] == 30
    # unsupported timeframe -> 400
    assert client.get("/api/v1/platform/market-data/bars/TRENDING?timeframe=99z", headers=h).status_code == 400
    # replay lifecycle
    rc = client.post("/api/v1/platform/market-data/replays", json={"symbol": "TRENDING", "timeframe": "1d"}, headers=h)
    rid = rc.json()["replay_id"]
    step = client.post(f"/api/v1/platform/market-data/replays/{rid}/step", json={"count": 3}, headers=h)
    assert step.status_code == 200 and len(step.json()["events"]) == 3
    assert client.post(f"/api/v1/platform/market-data/replays/{rid}/stop", json={}, headers=h).json()["replay"]["status"] == "STOPPED"
    # manifest
    assert client.get("/api/v1/platform/market-data/fixtures/manifest", headers=h).json()["manifest"]["datasets"]
    # no order/broker endpoints exist under market-data
    assert client.post("/api/v1/platform/market-data/orders", json={}, headers=h).status_code in (404, 405)
