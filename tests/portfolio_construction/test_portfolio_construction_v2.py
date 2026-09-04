"""PORTFOLIO-CONSTRUCTION-V2 adversarial contract tests.

These tests intentionally exercise the proposal boundary only.  No result in
this module is an order, an approval, a cash reservation, or a ledger write.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from saathi.platform.market_data.contract import (
    AssetClass,
    HistoricalBar,
    MarketStatus,
    PointInTime,
    ProviderReference,
)
from saathi.platform.portfolio_construction.engine import PortfolioConstructionEngine
from saathi.platform.portfolio_construction.models import (
    CandidatePortfolioStatus,
    ConstructionReasonCode,
    InstrumentMetadata,
    PortfolioConstructionRequest,
    PortfolioPosition,
    PortfolioSnapshotInput,
    ProposalStatus,
    StrategyQualificationEvidence,
    StrategyQualificationStatus,
)
from saathi.platform.portfolio_construction.tg_compose import (
    compose_candidate_with_tg,
    compose_proposal_with_tg,
)
from saathi.platform.fund_ledger.service import PortfolioLedgerService
from saathi.platform.fund_ledger.store import FundLedgerStore
from saathi.platform.portfolio_risk_engine.budget import PAPER_BUDGET_V2
from saathi.platform.portfolio_risk_engine.engine import PortfolioRiskEngine
from saathi.platform.portfolio_risk_engine.history import NavHistoryStore
from saathi.platform.trading_guardian import TradingGuardian
from saathi.platform.signal import Direction, TradingIntentProposal, TradingSignal
from saathi.platform.trading_models import (
    Account,
    DataQuality,
    Environment,
    MarketState,
    OrderIntent,
    OrderSide,
    OrderType,
)


NOW = datetime(2026, 1, 2, tzinfo=timezone.utc)
BTC = "BINANCE:BTC/USDT"
ETH = "BINANCE:ETH/USDT"
QUALIFICATION_ARTIFACT_SHA256 = (
    "45a115c978047e228c769d05cbef48e5d1a59070c94f4706dc2903f561bccd40"
)
DATASET_VERSION = (
    "sha256-0f1290db14ab0037e6a69e25bcd1d7928087629cf11630f0ac2c52dbb27768e8"
)


def _signal(
    instrument_id: str = BTC,
    *,
    direction: Direction = Direction.LONG_BIAS,
    strength: str = "0.50",
    strategy_id: str = "crypto_spot_mean_reversion",
    strategy_version: str = "1.0.0",
    quality: str = "VALID",
    valid_until: datetime | None = None,
) -> TradingSignal:
    return TradingSignal.create(
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        instrument_id=instrument_id,
        direction=direction,
        strength=strength,
        generated_at=NOW - timedelta(hours=1),
        valid_until=valid_until or NOW + timedelta(days=1),
        data_mode="HISTORICAL",
        reason_codes=("FROZEN_STRATEGY_OUTPUT",),
        quality=quality,
    )


def _qualification(
    signal: TradingSignal,
    status: StrategyQualificationStatus = StrategyQualificationStatus.PAPER_CANDIDATE,
) -> StrategyQualificationEvidence:
    return StrategyQualificationEvidence(
        intent_id="intent:" + signal.signal_id,
        signal_ref=signal.signal_id,
        strategy_id=signal.strategy_id,
        strategy_version=signal.strategy_version,
        instrument_id=signal.instrument_id,
        status=status,
        qualification_artifact_sha256=QUALIFICATION_ARTIFACT_SHA256,
        dataset_version=DATASET_VERSION,
        selected_config_hash="8ba2c7a6cf2d5423263493ed992996541122350d5a6f7245e56322429b2f6e72",
        quality="CERTIFIED_WITH_LIMITATIONS",
    )


def _meta(
    instrument_id: str = BTC,
    *,
    asset_class: AssetClass = AssetClass.CRYPTO,
    currency: str = "USDT",
    liquidity_limit_weight: Decimal | None = Decimal("0.15"),
    enabled: bool = True,
    venue_enabled: bool = True,
) -> InstrumentMetadata:
    symbol = "BTCUSDT" if instrument_id == BTC else "ETHUSDT"
    return InstrumentMetadata(
        instrument_id=instrument_id,
        symbol=symbol,
        venue="BINANCE" if asset_class == AssetClass.CRYPTO else "NEPSE",
        asset_class=asset_class,
        quote_currency=currency,
        enabled=enabled,
        venue_enabled=venue_enabled,
        liquidity_limit_weight=liquidity_limit_weight,
        estimated_round_trip_cost_bps=Decimal("40"),
    )


def _bars(
    instrument_id: str = BTC,
    *,
    pattern: tuple[Decimal, ...] = (Decimal("0.01"), Decimal("-0.01")),
    count: int = 100,
    future_jump: bool = False,
) -> tuple[HistoricalBar, ...]:
    rows: list[HistoricalBar] = []
    close = Decimal("100")
    start = NOW - timedelta(days=count + 1)
    for i in range(count):
        event_time = start + timedelta(days=i)
        close *= Decimal("1") + pattern[i % len(pattern)]
        rows.append(
            HistoricalBar(
                instrument_id=instrument_id,
                venue="BINANCE",
                asset_class=AssetClass.CRYPTO,
                currency="USDT",
                point_in_time=PointInTime(event_time, event_time, event_time, event_time),
                provider=ProviderReference("BINANCE_PUBLIC_DATA", provider_event_id=str(i)),
                quality=DataQuality.VALID,
                market_status=MarketStatus.CLOSED,
                open=close,
                high=close,
                low=close,
                close=close,
                volume=Decimal("1000"),
                timeframe="1d",
                source_record_id=f"{instrument_id}:{i}",
                revision_id="dataset-revision-1",
            )
        )
    if future_jump:
        event_time = NOW + timedelta(days=1)
        rows.append(
            replace(
                rows[-1],
                point_in_time=PointInTime(event_time, event_time, event_time, event_time),
                close=rows[-1].close * Decimal("10"),
                open=rows[-1].close * Decimal("10"),
                high=rows[-1].close * Decimal("10"),
                low=rows[-1].close * Decimal("10"),
                source_record_id=f"{instrument_id}:future",
            )
        )
    return tuple(rows)


def _snapshot(
    *,
    positions: tuple[PortfolioPosition, ...] = (),
    cash: str = "100000",
    available_cash: str | None = None,
    reserved_cash: str = "0",
    drawdown: str = "0",
    reconciliation_status: str = "HEALTHY",
) -> PortfolioSnapshotInput:
    return PortfolioSnapshotInput(
        fund_id="fund-v2",
        snapshot_ref="ledger-snapshot:1",
        reporting_currency="USDT",
        nav=Decimal("100000"),
        cash=Decimal(cash),
        available_cash=Decimal(available_cash if available_cash is not None else cash),
        reserved_cash=Decimal(reserved_cash),
        unsettled_cash=Decimal("0"),
        positions=positions,
        current_drawdown=Decimal(drawdown),
        source_authority="CANONICAL_FUND_LEDGER",
        reconciliation_status=reconciliation_status,
    )


def _position(
    instrument_id: str,
    weight: str,
    *,
    asset_class: AssetClass = AssetClass.CRYPTO,
) -> PortfolioPosition:
    value = Decimal("100000") * Decimal(weight)
    return PortfolioPosition(
        instrument_id=instrument_id,
        symbol="BTCUSDT" if instrument_id == BTC else "ETHUSDT",
        asset_class=asset_class,
        quote_currency="USDT",
        quantity=value / Decimal("100"),
        mark_price=Decimal("100"),
        market_value=value,
    )


def _request(
    *,
    signals: tuple[TradingSignal, ...] | None = None,
    qualifications: tuple[StrategyQualificationEvidence, ...] | None = None,
    metadata: tuple[InstrumentMetadata, ...] | None = None,
    snapshot: PortfolioSnapshotInput | None = None,
    histories: dict[str, tuple[HistoricalBar, ...]] | None = None,
    data_quality: str = "VALID",
    data_mode: str = "HISTORICAL",
    decision_time: datetime = NOW,
) -> PortfolioConstructionRequest:
    sigs = signals or (_signal(),)
    intents = tuple(TradingIntentProposal.from_signal(s) for s in sigs)
    quals = qualifications or tuple(_qualification(s) for s in sigs)
    metas = metadata or tuple(_meta(s.instrument_id) for s in sigs)
    history = histories or {s.instrument_id: _bars(s.instrument_id) for s in sigs}
    return PortfolioConstructionRequest.create(
        portfolio_snapshot=snapshot or _snapshot(),
        intents=intents,
        qualifications=quals,
        instrument_metadata=metas,
        market_history=history,
        market_data_snapshot_ref="market-data:certified:1",
        market_data_mode=data_mode,
        market_data_quality=data_quality,
        decision_time=decision_time,
        construction_policy_version="portfolio-construction/v2.0.0-configured-conservative",
        risk_budget_version=PAPER_BUDGET_V2.version,
    )


def _target(result, instrument_id: str = BTC) -> Decimal:
    row = next((x for x in result.allocations if x.instrument_id == instrument_id), None)
    return row.target_weight if row else Decimal("0")


def test_btc_paper_candidate_is_bounded_proposal_not_performance_sizing():
    result = PortfolioConstructionEngine().construct_from_intents(_request())

    assert result.status == CandidatePortfolioStatus.CANDIDATE_ALLOCATION
    assert Decimal("0") < _target(result) <= Decimal("0.15")
    assert _target(result) != Decimal("0.1895318557")
    assert result.cash_target_weight >= Decimal("0.05")
    public = result.to_public()
    assert public["proposal_state"] == "PROPOSED"
    assert public["authorizes_execution"] is False
    assert public["risk_approved"] is False
    assert "order_id" not in str(public).lower()
    assert "approval_id" not in str(public).lower()
    assert public["intent_ids"]
    assert public["strategy_ids"] == ["crypto_spot_mean_reversion"]
    assert public["qualification_artifact_sha256"] == [QUALIFICATION_ARTIFACT_SHA256]
    assert public["dataset_versions"] == [DATASET_VERSION]
    assert public["selected_config_hashes"] == [
        "8ba2c7a6cf2d5423263493ed992996541122350d5a6f7245e56322429b2f6e72"
    ]
    assert public["policy_assumption_status"] == "CONFIGURED_POLICY_ASSUMPTION"


def test_strength_and_untrusted_strategy_prose_have_no_sizing_authority():
    low = _signal(strength="0.01")
    high = _signal(strength="1")
    low_result = PortfolioConstructionEngine().construct_from_intents(_request(signals=(low,)))
    high_result = PortfolioConstructionEngine().construct_from_intents(_request(signals=(high,)))

    assert _target(low_result) == _target(high_result)
    assert not hasattr(TradingIntentProposal.from_signal(high), "requested_weight")


@pytest.mark.parametrize(
    "status",
    [
        StrategyQualificationStatus.OOS_VALIDATED_WITH_LIMITATIONS,
        StrategyQualificationStatus.RESEARCH_ONLY,
        StrategyQualificationStatus.REJECTED,
    ],
)
def test_non_paper_candidate_statuses_receive_zero_allocation(status):
    signal = _signal()
    req = _request(signals=(signal,), qualifications=(_qualification(signal, status),))
    result = PortfolioConstructionEngine().construct_from_intents(req)

    assert _target(result) == 0
    assert result.status == CandidatePortfolioStatus.ZERO_ALLOCATION
    assert ConstructionReasonCode.STRATEGY_NOT_ELIGIBLE in result.reason_codes


def test_existing_position_at_cap_does_not_increase():
    req = _request(snapshot=_snapshot(positions=(_position(BTC, "0.15"),), cash="85000"))
    result = PortfolioConstructionEngine().construct_from_intents(req)

    assert _target(result) == Decimal("0.15")
    assert ConstructionReasonCode.CURRENT_POSITION_AT_CAP in result.reason_codes


def test_existing_position_below_cap_moves_only_to_policy_target():
    req = _request(snapshot=_snapshot(positions=(_position(BTC, "0.04"),), cash="96000"))
    result = PortfolioConstructionEngine().construct_from_intents(req)

    assert _target(result) == Decimal("0.10")
    assert _target(result) <= Decimal("0.15")


def test_drawdown_scaling_is_monotonic_and_severe_drawdown_adds_no_risk():
    engine = PortfolioConstructionEngine()
    weights = [
        _target(engine.construct_from_intents(_request(snapshot=_snapshot(drawdown=d))))
        for d in ("0", "0.05", "0.10", "0.15")
    ]

    assert weights == sorted(weights, reverse=True)
    assert weights[-1] == 0
    assert ConstructionReasonCode.DRAWDOWN_REDUCTION in engine.construct_from_intents(
        _request(snapshot=_snapshot(drawdown="0.10"))
    ).reason_codes


def test_higher_volatility_never_increases_allocation():
    engine = PortfolioConstructionEngine()
    low = _request(histories={BTC: _bars(pattern=(Decimal("0.002"), Decimal("-0.002")))})
    normal = _request(histories={BTC: _bars(pattern=(Decimal("0.01"), Decimal("-0.01")))})
    high = _request(histories={BTC: _bars(pattern=(Decimal("0.04"), Decimal("-0.04")))})

    assert _target(engine.construct_from_intents(low)) >= _target(engine.construct_from_intents(normal))
    high_result = engine.construct_from_intents(high)
    assert _target(engine.construct_from_intents(normal)) >= _target(high_result)
    assert ConstructionReasonCode.VOLATILITY_REDUCTION in high_result.reason_codes


def test_high_or_missing_correlation_cannot_create_fake_diversification():
    snapshot = _snapshot(positions=(_position(ETH, "0.10"),), cash="90000")
    high = _request(
        snapshot=snapshot,
        metadata=(_meta(BTC), _meta(ETH)),
        histories={
            BTC: _bars(BTC, pattern=(Decimal("0.01"), Decimal("-0.01"))),
            ETH: _bars(ETH, pattern=(Decimal("0.01"), Decimal("-0.01"))),
        },
    )
    low = _request(
        snapshot=snapshot,
        metadata=(_meta(BTC), _meta(ETH)),
        histories={
            BTC: _bars(BTC, pattern=(Decimal("0.01"), Decimal("-0.01"))),
            ETH: _bars(ETH, pattern=(Decimal("0.01"), Decimal("0.01"), Decimal("-0.01"), Decimal("-0.01"))),
        },
    )
    missing = _request(snapshot=snapshot, metadata=(_meta(BTC), _meta(ETH)), histories={BTC: _bars(BTC)})
    engine = PortfolioConstructionEngine()
    low_result = engine.construct_from_intents(low)
    high_result = engine.construct_from_intents(high)
    missing_result = engine.construct_from_intents(missing)

    assert sum(x.target_weight for x in high_result.allocations) <= sum(
        x.target_weight for x in low_result.allocations
    )
    assert ConstructionReasonCode.CORRELATION_CONCENTRATION in high_result.reason_codes
    assert _target(missing_result) <= Decimal("0.05")
    assert ConstructionReasonCode.CORRELATION_DATA_INSUFFICIENT in missing_result.reason_codes


def test_cash_availability_and_reservations_protect_cash_floor():
    req = _request(
        snapshot=_snapshot(
            positions=(_position(ETH, "0.90", asset_class=AssetClass.EQUITY),),
            cash="10000",
            available_cash="4000",
            reserved_cash="6000",
        ),
        metadata=(_meta(BTC), _meta(ETH, asset_class=AssetClass.EQUITY)),
    )
    result = PortfolioConstructionEngine().construct_from_intents(req)

    assert _target(result) == 0
    assert result.cash_target_weight >= Decimal("0.05")
    assert ConstructionReasonCode.CASH_FLOOR in result.reason_codes


def test_crypto_sleeve_at_cap_allows_no_new_crypto_exposure():
    req = _request(
        snapshot=_snapshot(positions=(_position(ETH, "0.20"),), cash="80000"),
        metadata=(_meta(BTC), _meta(ETH)),
        histories={BTC: _bars(BTC), ETH: _bars(ETH)},
    )
    result = PortfolioConstructionEngine().construct_from_intents(req)

    assert _target(result) == 0
    assert ConstructionReasonCode.CRYPTO_SLEEVE_CAP in result.reason_codes


def test_conflicting_intents_hold_current_and_aligned_intents_do_not_sum():
    long_signal = _signal(strategy_id="crypto_spot_mean_reversion")
    reduce_signal = _signal(direction=Direction.REDUCE_BIAS, strategy_id="crypto_spot_trend")
    conflict = _request(
        signals=(long_signal, reduce_signal),
        qualifications=(_qualification(long_signal), _qualification(reduce_signal)),
        metadata=(_meta(BTC),),
        snapshot=_snapshot(positions=(_position(BTC, "0.04"),), cash="96000"),
    )
    aligned2 = _signal(strategy_id="crypto_spot_breakout")
    aligned = _request(
        signals=(long_signal, aligned2),
        qualifications=(_qualification(long_signal), _qualification(aligned2)),
        metadata=(_meta(BTC),),
    )
    engine = PortfolioConstructionEngine()
    conflict_result = engine.construct_from_intents(conflict)

    assert _target(conflict_result) == Decimal("0.04")
    assert ConstructionReasonCode.CONFLICTING_INTENTS in conflict_result.reason_codes
    assert _target(engine.construct_from_intents(aligned)) <= Decimal("0.10")


@pytest.mark.parametrize(
    ("quality", "mode"),
    [("STALE", "HISTORICAL"), ("VALID", "SYNTHETIC"), ("INVALID", "HISTORICAL")],
)
def test_bad_or_synthetic_market_data_fails_to_zero(quality, mode):
    result = PortfolioConstructionEngine().construct_from_intents(
        _request(data_quality=quality, data_mode=mode)
    )
    assert _target(result) == 0
    assert ConstructionReasonCode.DATA_QUALITY_INSUFFICIENT in result.reason_codes


def test_synthetic_signal_provenance_cannot_be_laundered_by_real_market_snapshot():
    signal = replace(_signal(), data_mode="SYNTHETIC")
    result = PortfolioConstructionEngine().construct_from_intents(
        _request(signals=(signal,), qualifications=(_qualification(signal),))
    )

    assert _target(result) == 0
    assert ConstructionReasonCode.DATA_QUALITY_INSUFFICIENT in result.reason_codes


def test_disabled_instrument_and_currency_confusion_fail_closed():
    disabled = PortfolioConstructionEngine().construct_from_intents(
        _request(metadata=(_meta(enabled=False),))
    )
    wrong_currency = PortfolioConstructionEngine().construct_from_intents(
        _request(metadata=(_meta(currency="USD"),))
    )

    assert _target(disabled) == 0
    assert ConstructionReasonCode.INSTRUMENT_DISABLED in disabled.reason_codes
    assert _target(wrong_currency) == 0
    assert ConstructionReasonCode.CURRENCY_MISMATCH in wrong_currency.reason_codes


def test_missing_liquidity_is_not_infinite_capacity():
    result = PortfolioConstructionEngine().construct_from_intents(
        _request(metadata=(_meta(liquidity_limit_weight=None),))
    )

    assert _target(result) <= Decimal("0.05")
    assert ConstructionReasonCode.LIQUIDITY_DATA_INSUFFICIENT in result.reason_codes


def test_tiny_rebalance_is_zeroed_after_cost_and_turnover_threshold():
    req = _request(snapshot=_snapshot(positions=(_position(BTC, "0.098"),), cash="90200"))
    result = PortfolioConstructionEngine().construct_from_intents(req)

    assert _target(result) == Decimal("0.098")
    assert ConstructionReasonCode.COST_INEFFICIENT_REBALANCE in result.reason_codes


def test_duplicate_authority_identities_are_rejected_not_silently_overwritten():
    signal = _signal()
    intent = TradingIntentProposal.from_signal(signal)
    qualification = _qualification(signal)
    with pytest.raises(ValueError, match="duplicate intent"):
        PortfolioConstructionRequest.create(
            portfolio_snapshot=_snapshot(),
            intents=(intent, intent),
            qualifications=(qualification,),
            instrument_metadata=(_meta(),),
            market_history={BTC: _bars()},
            market_data_snapshot_ref="market-data:certified:1",
            market_data_mode="HISTORICAL",
            market_data_quality="VALID",
            decision_time=NOW,
            construction_policy_version="portfolio-construction/v2.0.0-configured-conservative",
            risk_budget_version=PAPER_BUDGET_V2.version,
        )
    with pytest.raises(ValueError, match="duplicate instrument metadata"):
        PortfolioConstructionRequest.create(
            portfolio_snapshot=_snapshot(),
            intents=(intent,),
            qualifications=(qualification,),
            instrument_metadata=(_meta(), _meta()),
            market_history={BTC: _bars()},
            market_data_snapshot_ref="market-data:certified:1",
            market_data_mode="HISTORICAL",
            market_data_quality="VALID",
            decision_time=NOW,
            construction_policy_version="portfolio-construction/v2.0.0-configured-conservative",
            risk_budget_version=PAPER_BUDGET_V2.version,
        )


def test_unverified_qualification_cannot_unlock_candidate_capital():
    signal = _signal()
    qualification = replace(_qualification(signal), quality="UNVERIFIED")
    result = PortfolioConstructionEngine().construct_from_intents(
        _request(signals=(signal,), qualifications=(qualification,))
    )

    assert _target(result) == 0
    assert ConstructionReasonCode.STRATEGY_NOT_ELIGIBLE in result.reason_codes


def test_cash_component_accounting_cannot_exceed_ledger_cash():
    with pytest.raises(ValueError, match="available and reserved cash"):
        _snapshot(cash="10000", available_cash="9000", reserved_cash="2000")


def test_canonical_ledger_view_adapts_without_broker_account_or_cash_invention():
    view = {
        "fund_id": "fund-v2",
        "books_authority": "canonical_fund_ledger",
        "currency": "USDT",
        "nav": "100000",
        "cash": "80000",
        "available_cash": "75000",
        "reserved_cash": "5000",
        "positions": [
            {
                "security_id": BTC,
                "symbol": "BTCUSDT",
                "quantity": "200",
                "market_value": "20000",
                "mark_stale": False,
            }
        ],
        "invariants_ok": True,
    }
    snapshot = PortfolioSnapshotInput.from_ledger_view(
        view,
        instrument_metadata=(_meta(BTC),),
        snapshot_ref="ledger-view:sha256:test",
        current_drawdown=Decimal("0.03"),
        reconciliation_status="HEALTHY",
    )

    assert snapshot.source_authority == "CANONICAL_FUND_LEDGER"
    assert snapshot.available_cash == Decimal("75000")
    assert snapshot.reserved_cash == Decimal("5000")
    assert snapshot.positions[0].instrument_id == BTC
    assert snapshot.positions[0].market_value == Decimal("20000")
    assert not hasattr(snapshot, "broker_account")


def test_request_order_is_idempotent_and_candidate_identity_is_stable():
    btc = _signal(BTC)
    eth = _signal(ETH)
    kwargs = dict(
        signals=(btc, eth),
        qualifications=(_qualification(btc), _qualification(eth)),
        metadata=(_meta(BTC), _meta(ETH)),
        histories={BTC: _bars(BTC), ETH: _bars(ETH)},
    )
    a = PortfolioConstructionEngine().construct_from_intents(_request(**kwargs))
    kwargs["signals"] = (eth, btc)
    kwargs["qualifications"] = tuple(reversed(kwargs["qualifications"]))
    kwargs["metadata"] = tuple(reversed(kwargs["metadata"]))
    b = PortfolioConstructionEngine().construct_from_intents(_request(**kwargs))

    assert a.candidate_portfolio_id == b.candidate_portfolio_id
    assert a.to_public() == b.to_public()


def test_future_bar_is_excluded_from_volatility_estimate():
    base = PortfolioConstructionEngine().construct_from_intents(_request(histories={BTC: _bars(BTC)}))
    future = PortfolioConstructionEngine().construct_from_intents(
        _request(histories={BTC: _bars(BTC, future_jump=True)})
    )

    assert _target(base) == _target(future)
    assert ConstructionReasonCode.FUTURE_DATA_EXCLUDED in future.reason_codes


def test_guardian_composition_fails_closed_when_guardian_cannot_run():
    proposal = {
        "proposal_id": "p1",
        "status": ProposalStatus.READY_FOR_APPROVAL.value,
        "trades": [
            {
                "symbol": "BTCUSDT",
                "action": "BUY",
                "reference_price": "100",
                "estimated_quantity": "10",
            }
        ],
    }
    result = compose_proposal_with_tg(
        proposal=proposal,
        guardian=object(),
        risk_engine=object(),
        account=object(),
        fund_id="fund-v2",
        intent_factory=None,
    )

    assert result["governance_allowed"] is False
    assert result["authorizes_execution"] is False


def test_no_intent_means_zero_allocation_not_forced_investment():
    req = PortfolioConstructionRequest.create(
        portfolio_snapshot=_snapshot(),
        intents=(),
        qualifications=(),
        instrument_metadata=(_meta(),),
        market_history={BTC: _bars()},
        market_data_snapshot_ref="market-data:certified:1",
        market_data_mode="HISTORICAL",
        market_data_quality="VALID",
        decision_time=NOW,
        construction_policy_version="portfolio-construction/v2.0.0-configured-conservative",
        risk_budget_version=PAPER_BUDGET_V2.version,
    )
    result = PortfolioConstructionEngine().construct_from_intents(req)

    assert result.status == CandidatePortfolioStatus.ZERO_ALLOCATION
    assert result.cash_target_weight == Decimal("1")


def _risk_fixture(max_trade_notional: str = "10000"):
    ledger = PortfolioLedgerService(FundLedgerStore(":memory:"))
    ledger.create_fund(fund_id="fund-v2", opening_cash="100000")
    risk = PortfolioRiskEngine(
        budget=replace(PAPER_BUDGET_V2, max_trade_notional=Decimal(max_trade_notional)),
        history=NavHistoryStore(),
        get_ledger_state=lambda fund_id: ledger.get_state(fund_id),
        get_recon_status=lambda fund_id: {"ok": True, "portfolio_status": "HEALTHY"},
    )
    account = Account("paper-account", Environment.PAPER, Decimal("100000"), currency="USDT")
    return ledger, risk, account


def _order_intent(trade) -> OrderIntent:
    return OrderIntent(
        intent_id="guardian-dry-run:" + trade["symbol"],
        org_id="org-test",
        workspace_id="workspace-test",
        account_id="paper-account",
        environment=Environment.PAPER,
        symbol=trade["symbol"],
        side=OrderSide(trade["action"]),
        order_type=OrderType.MARKET,
        quantity=Decimal(trade["estimated_quantity"]),
        idempotency_key="dry-run-idempotency",
        approval_id="preexisting-paper-approval-ref",
        strategy_id="crypto_spot_mean_reversion",
        strategy_version=1,
    )


def test_candidate_handoff_uses_canonical_risk_and_guardian_without_execution():
    request = _request()
    engine = PortfolioConstructionEngine()
    candidate = engine.construct_from_intents(request)
    ledger, risk, account = _risk_fixture()
    handoff = engine.build_risk_handoff(request, candidate)

    assert len(handoff) == 1
    assert handoff[0].side == "BUY"
    result = compose_candidate_with_tg(
        engine=engine,
        request=request,
        candidate=candidate,
        guardian=TradingGuardian(),
        risk_engine=risk,
        account=account,
        fund_id="fund-v2",
        ledger_state=ledger.get_state("fund-v2"),
        recon={"ok": True, "portfolio_status": "HEALTHY"},
        intent_factory=_order_intent,
    )

    assert result["governance_allowed"] is True
    assert result["authorizes_execution"] is False
    assert result["risk_approved"] is False
    assert result["execution_reachable"] is False


@pytest.mark.parametrize("failure", ["stale", "reconciliation", "risk", "kill_switch"])
def test_guardian_and_risk_remain_independent_fail_closed_vetoes(failure):
    request = _request()
    engine = PortfolioConstructionEngine()
    candidate = engine.construct_from_intents(request)
    ledger, risk, account = _risk_fixture("5000" if failure == "risk" else "10000")
    guardian = TradingGuardian()
    quality = DataQuality.VALID
    recon = {"ok": True, "portfolio_status": "HEALTHY"}
    if failure == "stale":
        quality = DataQuality.STALE
    elif failure == "reconciliation":
        recon = {"ok": False, "portfolio_status": "RECONCILIATION_REQUIRED"}
    elif failure == "kill_switch":
        guardian.trip("operator kill switch")

    result = compose_candidate_with_tg(
        engine=engine,
        request=request,
        candidate=candidate,
        guardian=guardian,
        risk_engine=risk,
        account=account,
        fund_id="fund-v2",
        ledger_state=ledger.get_state("fund-v2"),
        recon=recon,
        intent_factory=_order_intent,
        price_quality=quality,
        market_state=MarketState.OPEN,
    )

    assert result["governance_allowed"] is False
    assert result["authorizes_execution"] is False
    assert result["execution_reachable"] is False


def test_zero_candidate_cannot_be_presented_as_governance_allowed():
    signal = _signal()
    request = _request(
        signals=(signal,),
        qualifications=(_qualification(signal, StrategyQualificationStatus.REJECTED),),
    )
    engine = PortfolioConstructionEngine()
    candidate = engine.construct_from_intents(request)
    ledger, risk, account = _risk_fixture()

    result = compose_candidate_with_tg(
        engine=engine,
        request=request,
        candidate=candidate,
        guardian=TradingGuardian(),
        risk_engine=risk,
        account=account,
        fund_id="fund-v2",
        ledger_state=ledger.get_state("fund-v2"),
        recon={"ok": True, "portfolio_status": "HEALTHY"},
        intent_factory=_order_intent,
    )

    assert result["governance_allowed"] is False
    assert result["reason"] == "NO_MATERIAL_CANDIDATE_CHANGE"
