"""ATTRIBUTION-V2 — multi-dimension attribution invariants."""
from decimal import Decimal

from saathi.platform.tg.attribution_v2 import (
    AttributionRecord, AttributionStatus, attribute, max_drawdown, reconciles,
)


def _rec(strategy="crypto_spot_mean_reversion", symbol="BTCUSDT", venue="CRYPTO",
         asset_class="CRYPTO", gross="100", cost="10", benchmark=None, blocked=False):
    return AttributionRecord(
        strategy_id=strategy, symbol=symbol, venue=venue, asset_class=asset_class,
        gross_pnl=Decimal(gross), cost=Decimal(cost),
        benchmark_pnl=None if benchmark is None else Decimal(benchmark),
        guardian_blocked=blocked,
    )


def test_empty_is_data_insufficient_not_zero():
    r = attribute([])
    assert r["status"] == AttributionStatus.DATA_INSUFFICIENT.value


def test_totals_and_cost_drag():
    r = attribute([_rec(gross="100", cost="10"), _rec(gross="50", cost="5")])
    assert r["totals"]["gross_pnl"] == Decimal("150")
    assert r["totals"]["cost_drag"] == Decimal("15")
    assert r["totals"]["net_pnl"] == Decimal("135")


def test_every_dimension_reconciles_to_net():
    recs = [
        _rec(strategy="s1", symbol="BTCUSDT", venue="CRYPTO", gross="100", cost="10"),
        _rec(strategy="s2", symbol="ETHUSDT", venue="CRYPTO", gross="40", cost="4"),
        _rec(strategy="s1", symbol="NEPSE:NABIL", venue="NEPSE",
             asset_class="EQUITY", gross="20", cost="2"),
    ]
    r = attribute(recs)
    assert reconciles(r) is True
    assert set(r["by_strategy"]) == {"s1", "s2"}
    assert set(r["by_venue"]) == {"CRYPTO", "NEPSE"}
    assert r["by_venue"]["NEPSE"]["net"] == Decimal("18")


def test_guardian_blocked_records_claim_no_pnl():
    recs = [_rec(gross="100", cost="10"), _rec(symbol="ETHUSDT", gross="999", cost="0", blocked=True)]
    r = attribute(recs)
    assert r["totals"]["net_pnl"] == Decimal("90")  # blocked PnL not claimed
    assert r["guardian"]["blocked_count"] == 1
    assert r["guardian"]["blocked_symbols"] == ["ETHUSDT"]


def test_partial_benchmark_is_data_insufficient_not_silently_zero():
    r = attribute([_rec(benchmark="50"), _rec(benchmark=None)])
    assert r["benchmark"]["status"] == AttributionStatus.DATA_INSUFFICIENT.value
    assert r["benchmark"]["benchmark_pnl"] is None


def test_full_benchmark_gives_excess():
    r = attribute([_rec(gross="100", cost="10", benchmark="50")])
    assert r["benchmark"]["status"] == AttributionStatus.OK.value
    assert r["benchmark"]["excess_vs_benchmark"] == Decimal("40")  # 90 net - 50 bench


def test_drawdown_from_equity_path():
    assert max_drawdown(["0", "100", "40", "60"]) == Decimal("60")
    r = attribute([_rec()], equity_path=["0", "100", "40"])
    assert r["risk"]["max_drawdown"] == Decimal("60")


def test_missing_equity_path_is_data_insufficient():
    r = attribute([_rec()])
    assert r["risk"]["status"] == AttributionStatus.DATA_INSUFFICIENT.value
    assert r["risk"]["max_drawdown"] is None


def test_attribution_has_no_execution_authority():
    r = attribute([_rec()])
    assert r["authorizes_execution"] is False
    assert r["label"] == "RESEARCH_ATTRIBUTION_NOT_OFFICIAL_GIPS"
