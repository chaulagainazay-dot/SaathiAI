from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from saathi.platform.backtest.cost import CryptoCostModel
from saathi.platform.backtest.strategy_crypto import (
    CANONICAL_CRYPTO_INSTRUMENTS,
    CryptoDatasetSnapshot,
    CryptoQualificationRunner,
    FinalTestLedger,
    QualificationStatus,
    RegisteredSpotStrategyRegistry,
    RejectionReason,
    SelectionBiasStatus,
    StrategyFamily,
    TestWindowSpentError,
    build_public_binance_snapshot,
    dataset_content_hash,
    qualify_crypto_universe,
)
from saathi.platform.market_data.contract import (
    AssetClass,
    HistoricalBar,
    PointInTime,
    ProviderReference,
)
from saathi.platform.signal import Direction, TradingSignal
from saathi.platform.trading_models import DataQuality


T0 = datetime(2021, 1, 1, tzinfo=timezone.utc)
BTC = "BINANCE:BTC/USDT"
ETH = "BINANCE:ETH/USDT"


def make_bars(
    instrument_id: str = BTC,
    *,
    count: int = 260,
    test_shock: Decimal = Decimal("0"),
) -> tuple[HistoricalBar, ...]:
    rows = []
    previous = Decimal("100")
    for index in range(count):
        wave = Decimal((index % 12) - 6) / Decimal("10")
        close = Decimal("100") + Decimal(index) * Decimal("0.18") + wave
        if index >= int(count * 0.8):
            close += test_shock * Decimal(index - int(count * 0.8))
        opened = previous
        high = max(opened, close) + Decimal("1")
        low = min(opened, close) - Decimal("1")
        as_of = T0 + timedelta(days=index)
        rows.append(
            HistoricalBar(
                instrument_id=instrument_id,
                venue="BINANCE",
                asset_class=AssetClass.CRYPTO,
                currency="USDT",
                point_in_time=PointInTime(
                    event_timestamp=as_of - timedelta(days=1),
                    as_of=as_of,
                    available_at=as_of,
                    received_at=T0 + timedelta(days=400),
                ),
                provider=ProviderReference(
                    provider="DETERMINISTIC_TEST_FIXTURE",
                    provider_event_id=f"bar-{index}",
                    sequence=index,
                    source_ref="tests/backtest/test_strategy_crypto.py",
                    is_delayed=True,
                ),
                quality=DataQuality.VALID,
                source_record_id=f"bar-{index}",
                revision_id=f"r-{index}",
                open=opened,
                high=high,
                low=low,
                close=close,
                volume=Decimal("1000"),
            )
        )
        previous = close
    return tuple(rows)


def snapshot(
    instrument_id: str = BTC,
    *,
    mode: str = "SYNTHETIC",
    quality: str = "SYNTHETIC_TEST_ONLY",
    bars: tuple[HistoricalBar, ...] | None = None,
) -> CryptoDatasetSnapshot:
    rows = bars or make_bars(instrument_id)
    return CryptoDatasetSnapshot(
        dataset_id=f"dataset:{instrument_id}",
        dataset_version="sha256:test-v1",
        instrument_id=instrument_id,
        data_mode=mode,
        source="DETERMINISTIC_TEST_FIXTURE",
        quality_classification=quality,
        revision_snapshot="snapshot:test-v1",
        revision_cutoff=T0 + timedelta(days=400),
        content_hash=dataset_content_hash(rows),
    )


def runner(instrument_id: str = BTC, **kwargs) -> CryptoQualificationRunner:
    rows = make_bars(instrument_id, **kwargs)
    return CryptoQualificationRunner(
        snapshot(instrument_id, bars=rows),
        rows,
    )


def test_preregistration_is_bounded_and_complete_before_selection():
    hypotheses = runner().preregistrations()
    assert len(hypotheses) == 3
    assert {item.family for item in hypotheses} == set(StrategyFamily)
    assert all(len(item.parameter_search_space) <= 4 for item in hypotheses)
    assert all(item.trial_budget == 12 for item in hypotheses)
    assert all(item.benchmark == "SAME_INSTRUMENT_SPOT_BUY_AND_HOLD" for item in hypotheses)
    assert all(item.evaluation_plan.test_start >= item.evaluation_plan.validation_end for item in hypotheses)
    assert all(item.rejection_conditions for item in hypotheses)
    with pytest.raises(TypeError):
        hypotheses[0].parameter_search_space[0]["fast_lookback"] = 2


def test_parameter_budget_cannot_be_expanded_after_preregistration():
    run = runner()
    hypothesis = run.preregistrations()[0]
    expanded = replace(
        hypothesis,
        parameter_search_space=(*hypothesis.parameter_search_space, hypothesis.parameter_search_space[0]),
        trial_budget=13,
    )
    with pytest.raises(ValueError, match="parameter budget"):
        run.qualify(expanded)


def test_only_registered_spot_strategies_and_canonical_instruments_are_accepted():
    hypotheses = runner().preregistrations()
    registry = RegisteredSpotStrategyRegistry()
    strategy = registry.create(hypotheses[0].strategy_id, hypotheses[0].parameter_search_space[0])
    assert strategy.family is StrategyFamily.TREND_MOMENTUM
    with pytest.raises(ValueError, match="registered"):
        registry.create("os.system('trade')", hypotheses[0].parameter_search_space[0])
    with pytest.raises(ValueError, match="spot instrument"):
        replace(snapshot(), instrument_id="BINANCE:BTCUSDT-PERP")
    assert CANONICAL_CRYPTO_INSTRUMENTS == (BTC, ETH)


def test_every_strategy_output_is_canonical_signal_without_execution_authority():
    run = runner()
    for hypothesis in run.preregistrations():
        strategy = RegisteredSpotStrategyRegistry().create(
            hypothesis.strategy_id,
            hypothesis.parameter_search_space[0],
        )
        signal = strategy.evaluate(run.visible_history_at(run.bars[100].as_of), data_mode="SYNTHETIC")
        assert isinstance(signal, TradingSignal)
        assert signal.direction in set(Direction)
        for forbidden in ("quantity", "order", "cash_reservation", "execution_gateway"):
            assert not hasattr(signal, forbidden)


def test_breakout_uses_prior_range_and_never_fills_on_the_decision_bar():
    rows = list(make_bars(count=260))
    decision_index = 100
    prior_high = max(row.high for row in rows[80:decision_index])
    current = rows[decision_index]
    rows[decision_index] = replace(
        current,
        open=prior_high,
        high=prior_high + Decimal("20"),
        low=prior_high - Decimal("1"),
        close=prior_high + Decimal("1"),
    )
    run = CryptoQualificationRunner(snapshot(bars=tuple(rows)), rows)
    hypothesis = next(h for h in run.preregistrations() if h.family is StrategyFamily.BREAKOUT)
    strategy = RegisteredSpotStrategyRegistry().create(
        hypothesis.strategy_id,
        {"lookback": 20, "confirmation": "0", "exit_lookback": 10},
    )
    signal = strategy.evaluate(run.visible_history_at(rows[decision_index].as_of), data_mode="SYNTHETIC")
    assert signal.direction is Direction.LONG_BIAS
    segment = run.run_segment(
        strategy,
        start_index=decision_index,
        end_index=decision_index + 4,
        cost_model=CryptoCostModel(),
    )
    assert segment.fills
    assert all(fill.fill_at > fill.decision_at for fill in segment.fills)
    assert segment.fills[0].reference_price == rows[decision_index + 1].open


def test_revision_published_after_snapshot_or_decision_cannot_leak():
    rows = list(make_bars())
    future = replace(
        rows[10],
        revision_id="future-correction",
        close=Decimal("999999"),
        high=Decimal("1000000"),
        point_in_time=replace(
            rows[10].point_in_time,
            available_at=T0 + timedelta(days=390),
            received_at=T0 + timedelta(days=400),
        ),
        supersedes_revision_id=rows[10].revision_id,
        status="CORRECTED",
    )
    all_rows = tuple([*rows, future])
    run = CryptoQualificationRunner(snapshot(bars=all_rows), all_rows)
    history = run.visible_history_at(T0 + timedelta(days=200))
    assert next(row for row in history if row.source_record_id == "bar-10").revision_id != "future-correction"
    assert all(row.available_at <= T0 + timedelta(days=200) for row in history)


def test_dataset_content_hash_mismatch_fails_closed():
    with pytest.raises(ValueError, match="content hash"):
        CryptoQualificationRunner(replace(snapshot(), content_hash="0" * 64), make_bars())


def test_public_binance_adapter_rows_become_closed_revision_limited_spot_bars():
    class PublicBar:
        def __init__(self, index: int):
            self.ts = (T0 + timedelta(days=index)).timestamp()
            self.open = Decimal("100") + index
            self.high = Decimal("102") + index
            self.low = Decimal("99") + index
            self.close = Decimal("101") + index
            self.volume = Decimal("1000")

    retrieved_at = T0 + timedelta(days=7, hours=12)
    dataset, rows = build_public_binance_snapshot(
        BTC,
        [PublicBar(index) for index in range(8)],
        retrieved_at=retrieved_at,
    )
    assert len(rows) == 7
    assert all(row.as_of <= retrieved_at for row in rows)
    assert dataset.quality_classification == "REAL_PUBLIC_HISTORICAL_REVISION_SNAPSHOT"
    assert "LEGACY_LATEST_ONLY_DATASET" in dataset.limitations
    assert dataset.content_hash == dataset_content_hash(rows)
    assert CryptoQualificationRunner(dataset, rows).dataset.instrument_id == BTC


def test_zero_cost_qualification_is_forbidden_and_invalid_side_fails_closed():
    zero = CryptoCostModel(fee_bps=0, spread_bps=0, slippage_bps=0)
    with pytest.raises(ValueError, match="zero-cost"):
        CryptoQualificationRunner(snapshot(), make_bars(), cost_model=zero)
    with pytest.raises(ValueError, match="side"):
        CryptoCostModel().fill_price("SHORT", Decimal("101"), Decimal("99"))


def test_validation_selection_does_not_observe_or_change_with_final_test():
    base = runner()
    shocked_rows = make_bars(test_shock=Decimal("20"))
    shocked = CryptoQualificationRunner(snapshot(bars=shocked_rows), shocked_rows)
    for left_hypothesis, right_hypothesis in zip(base.preregistrations(), shocked.preregistrations()):
        left = base.select_and_lock(left_hypothesis)
        right = shocked.select_and_lock(right_hypothesis)
        assert left.config_hash == right.config_hash
        assert left.parameters == right.parameters


def test_final_test_ledger_allows_reproduction_but_rejects_retuning_same_window():
    ledger = FinalTestLedger()
    window = (T0 + timedelta(days=200), T0 + timedelta(days=259))
    ledger.record("BTC:TREND", window, "config-a")
    ledger.record("BTC:TREND", window, "config-a")
    with pytest.raises(TestWindowSpentError):
        ledger.record("BTC:TREND", window, "config-b")


def test_synthetic_evidence_never_promotes_and_trial_counts_are_exact():
    result = runner().qualify_all()
    assert result.certification_outcome == "STRATEGY_RESEARCH_BLOCKED_DATA_QUALITY"
    assert result.family_count == 3
    assert result.total_trial_count == 36
    assert all(item.trial_count == 12 for item in result.results)
    assert all(item.qualification_status is not QualificationStatus.PAPER_CANDIDATE for item in result.results)
    assert all("SYNTHETIC_ONLY_EVIDENCE" in item.limitations for item in result.results)
    assert all(item.selection_bias_status is SelectionBiasStatus.MULTIPLE_TESTING_LIMITED for item in result.results)


def test_result_reports_required_metrics_cost_sensitivity_walk_forward_and_stress():
    result = runner().qualify_all().results[0]
    metrics = result.test_result
    for field in (
        "gross_return",
        "net_return",
        "benchmark_return",
        "excess_return",
        "max_drawdown",
        "volatility",
        "turnover",
        "trade_count",
        "cost_drag",
        "hit_rate",
        "average_holding_period",
    ):
        assert hasattr(metrics, field)
    assert {row.scenario for row in result.cost_sensitivity} == {
        "BASE_COSTS",
        "DOUBLE_FEES",
        "DOUBLE_SPREAD",
        "DOUBLE_SLIPPAGE",
    }
    assert len(result.walk_forward_result.segments) == 2
    assert {row.scenario for row in result.stress_results} >= {
        "DELAYED_FILL",
        "MISSING_OBSERVATIONS",
        "LIQUIDITY_DEGRADATION",
        "OBSERVED_VOLATILITY_SPIKE_REGIME",
    }


def test_btc_and_eth_are_qualified_separately_without_cross_asset_selection():
    eth_bars = make_bars(ETH, test_shock=Decimal("-2"))
    result = qualify_crypto_universe(
        {
            BTC: (snapshot(BTC), make_bars(BTC)),
            ETH: (snapshot(ETH, bars=eth_bars), eth_bars),
        }
    )
    assert result.instrument_count == 2
    assert result.family_count == 3
    assert len(result.results) == 6
    assert {item.instrument_id for item in result.results} == {BTC, ETH}
    assert result.total_trial_count == 72


def test_insufficient_history_is_research_only_with_explicit_rejection_reason():
    short_rows = make_bars(count=80)
    short = CryptoQualificationRunner(snapshot(bars=short_rows), short_rows)
    result = short.qualify_all()
    assert all(item.qualification_status is QualificationStatus.RESEARCH_ONLY for item in result.results)
    assert all(RejectionReason.INSUFFICIENT_DATA in item.rejection_reasons for item in result.results)


def test_exact_experiment_is_deterministic_and_has_no_live_ready_state():
    first = runner().qualify_all().to_public()
    second = runner().qualify_all().to_public()
    assert first == second
    assert "LIVE_READY" not in repr(first)
    assert first["authority"]["live_trading"] is False
    assert first["authority"]["private_account_access"] is False
    assert first["authority"]["leverage"] is False
