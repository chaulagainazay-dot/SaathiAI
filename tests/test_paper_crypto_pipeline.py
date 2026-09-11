"""PAPER-CRYPTO-2 — canonical paper cycle chain invariants.

Drives the REAL certified authorities (construction -> risk -> guardian venue ->
approval) and proves the chain refuses at the right boundary every time.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from saathi.platform.market_data.contract import (
    AssetClass, HistoricalBar, MarketStatus, PointInTime, ProviderReference,
)
from saathi.platform.portfolio_construction.models import (
    InstrumentMetadata, PortfolioConstructionRequest, PortfolioSnapshotInput,
    StrategyQualificationEvidence, StrategyQualificationStatus,
)
from saathi.platform.portfolio_risk_engine.budget import PAPER_BUDGET_V2
from saathi.platform.signal import Direction, TradingIntentProposal, TradingSignal
from saathi.platform.trading_models import DataQuality
from saathi.platform.tg.paper_crypto_pipeline import (
    PaperCryptoPipeline, PaperCycleOutcome, PaperCycleStage,
)

NOW = datetime(2026, 1, 2, tzinfo=timezone.utc)
BTC = "BINANCE:BTC/USDT"
QUAL_SHA = "45a115c978047e228c769d05cbef48e5d1a59070c94f4706dc2903f561bccd40"
DATASET_VERSION = "sha256-0f1290db14ab0037e6a69e25bcd1d7928087629cf11630f0ac2c52dbb27768e8"
CONFIG_HASH = "8ba2c7a6cf2d5423263493ed992996541122350d5a6f7245e56322429b2f6e72"


def _signal(instrument_id=BTC, strength="0.50"):
    return TradingSignal.create(
        strategy_id="crypto_spot_mean_reversion", strategy_version="1.0.0",
        instrument_id=instrument_id, direction=Direction.LONG_BIAS, strength=strength,
        generated_at=NOW - timedelta(hours=1), valid_until=NOW + timedelta(days=1),
        data_mode="HISTORICAL", reason_codes=("FROZEN_STRATEGY_OUTPUT",), quality="VALID",
    )


def _qualification(signal, status=StrategyQualificationStatus.PAPER_CANDIDATE):
    return StrategyQualificationEvidence(
        intent_id="intent:" + signal.signal_id, signal_ref=signal.signal_id,
        strategy_id=signal.strategy_id, strategy_version=signal.strategy_version,
        instrument_id=signal.instrument_id, status=status,
        qualification_artifact_sha256=QUAL_SHA, dataset_version=DATASET_VERSION,
        selected_config_hash=CONFIG_HASH, quality="CERTIFIED_WITH_LIMITATIONS",
    )


def _meta(instrument_id=BTC):
    return InstrumentMetadata(
        instrument_id=instrument_id, symbol="BTCUSDT", venue="BINANCE",
        asset_class=AssetClass.CRYPTO, quote_currency="USDT", enabled=True,
        venue_enabled=True, liquidity_limit_weight=Decimal("0.15"),
        estimated_round_trip_cost_bps=Decimal("40"),
    )


def _bars(instrument_id=BTC, count=100):
    rows = []
    close = Decimal("100")
    pattern = (Decimal("0.01"), Decimal("-0.01"))
    for i in range(count):
        close = close * (Decimal("1") + pattern[i % len(pattern)])
        event_time = NOW - timedelta(days=count + 1 - i)
        rows.append(HistoricalBar(
            instrument_id=instrument_id,
            venue="BINANCE",
            asset_class=AssetClass.CRYPTO,
            currency="USDT",
            point_in_time=PointInTime(event_time, event_time, event_time, event_time),
            provider=ProviderReference("BINANCE_PUBLIC_DATA", provider_event_id=str(i)),
            quality=DataQuality.VALID, market_status=MarketStatus.CLOSED,
            open=close, high=close, low=close, close=close, volume=Decimal("1000"),
            timeframe="1d", source_record_id=f"{instrument_id}:{i}",
            revision_id="dataset-revision-1",
        ))
    return tuple(rows)


def _snapshot(cash="100000", reconciliation_status="HEALTHY"):
    return PortfolioSnapshotInput(
        fund_id="fund-v2", snapshot_ref="ledger-snapshot:1", reporting_currency="USDT",
        nav=Decimal("100000"), cash=Decimal(cash), available_cash=Decimal(cash),
        reserved_cash=Decimal("0"), unsettled_cash=Decimal("0"), positions=(),
        current_drawdown=Decimal("0"), source_authority="CANONICAL_FUND_LEDGER",
        reconciliation_status=reconciliation_status,
    )


def _request(signals=None, qualifications=None, snapshot=None):
    sigs = signals or (_signal(),)
    intents = tuple(TradingIntentProposal.from_signal(s) for s in sigs)
    quals = qualifications or tuple(_qualification(s) for s in sigs)
    return PortfolioConstructionRequest.create(
        portfolio_snapshot=snapshot or _snapshot(), intents=intents, qualifications=quals,
        instrument_metadata=tuple(_meta(s.instrument_id) for s in sigs),
        market_history={s.instrument_id: _bars(s.instrument_id) for s in sigs},
        market_data_snapshot_ref="market-data:certified:1", market_data_mode="HISTORICAL",
        market_data_quality="VALID", decision_time=NOW,
        construction_policy_version="portfolio-construction/v2.0.0-configured-conservative",
        risk_budget_version=PAPER_BUDGET_V2.version,
    )


# ── chain behaviour ──────────────────────────────────────────────────────────────
def test_approval_is_never_self_granted():
    snap = _snapshot()
    dec = PaperCryptoPipeline().run(_request(snapshot=snap), portfolio_snapshot=snap)
    assert dec.stage == PaperCycleStage.APPROVAL
    assert dec.outcome == PaperCycleOutcome.APPROVAL_REQUIRED
    assert dec.ready is False
    assert dec.authorizes_execution is False


def test_guardian_venue_blocks_even_when_construction_and_risk_pass():
    snap = _snapshot()
    dec = PaperCryptoPipeline().run(
        _request(snapshot=snap), portfolio_snapshot=snap, disabled_venues=["CRYPTO"],
    )
    assert dec.stage == PaperCycleStage.GUARDIAN_VENUE
    assert dec.outcome == PaperCycleOutcome.BLOCKED_GUARDIAN
    assert "VENUE_DISABLED" in dec.reason_codes
    assert dec.risk_result == "ALLOW"  # risk had already passed


def test_non_paper_candidate_gets_zero_allocation_not_execution():
    sig = _signal()
    snap = _snapshot()
    dec = PaperCryptoPipeline().run(
        _request(signals=(sig,),
                 qualifications=(_qualification(sig, StrategyQualificationStatus.REJECTED),),
                 snapshot=snap),
        portfolio_snapshot=snap, approval_granted=True,
    )
    assert dec.outcome == PaperCycleOutcome.NO_ALLOCATION
    assert dec.planned_orders == ()


def test_approved_cycle_yields_plan_but_never_authorizes_execution():
    snap = _snapshot()
    dec = PaperCryptoPipeline().run(
        _request(snapshot=snap), portfolio_snapshot=snap, approval_granted=True,
        price_map={"BTCUSDT": "100"},
    )
    assert dec.outcome == PaperCycleOutcome.READY_FOR_EXECUTION_GATEWAY
    assert dec.ready is True
    assert dec.authorizes_execution is False
    assert dec.to_public()["authorizes_execution"] is False
    assert dec.to_public()["mode"] == "PAPER"
    order = dec.planned_orders[0]
    assert order.symbol == "BTCUSDT"
    assert order.venue == "CRYPTO"
    assert order.quantity is not None and order.quantity > 0


def test_plan_quantity_is_venue_normalized():
    snap = _snapshot()
    dec = PaperCryptoPipeline().run(
        _request(snapshot=snap), portfolio_snapshot=snap, approval_granted=True,
        price_map={"BTCUSDT": "3"},  # forces a non-terminating division
    )
    qty = dec.planned_orders[0].quantity
    # crypto step is 1e-6: quantity must be an exact multiple of the step
    assert (qty % Decimal("0.000001")) == 0


def test_pipeline_exposes_no_execution_entrypoint():
    pipe = PaperCryptoPipeline()
    for banned in ("submit", "execute", "send_order", "approve"):
        assert not hasattr(pipe, banned)


def test_session_bound_venue_unknown_session_fails_closed():
    snap = _snapshot()
    dec = PaperCryptoPipeline().run(
        _request(snapshot=snap), portfolio_snapshot=snap,
        require_session=True, session_open=None,
    )
    assert dec.outcome == PaperCycleOutcome.BLOCKED_GUARDIAN
    assert "VENUE_SESSION_UNKNOWN" in dec.reason_codes
