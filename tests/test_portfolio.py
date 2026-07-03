"""Portfolio Intelligence tests (M5 Phase 4) — deterministic wealth-as-a-system.

Verifies the six engines, the Impact Simulator (evaluate in-portfolio, no
mutation), and the Capital Reserve Engine (financial vs business competition).
"""
import pytest

from saathi.investment import AssetClass
from saathi.portfolio import (
    Position, PortfolioRegistry,
    AllocationEngine, DiversificationEngine, PortfolioRiskEngine,
    PortfolioHealthScore, RebalancingEngine,
    PortfolioImpactSimulator,
    CapitalReserveEngine, ReserveOption, ReserveKind,
)


def _reg():
    r = PortfolioRegistry(cash_usd=10_000, emergency_fund_usd=5_000)
    r.positions = [
        Position("BTC", AssetClass.CRYPTO, 30_000, sector="crypto", volatility=0.6,
                 liquidity=0.95, cost_basis_usd=20_000),
        Position("SPY", AssetClass.ETF, 40_000, sector="broad_equity", volatility=0.15,
                 liquidity=0.99, cost_basis_usd=38_000),
        Position("Cafeteria", AssetClass.OWN_BUSINESS, 20_000, sector="food",
                 volatility=0.25, liquidity=0.1, cost_basis_usd=20_000),
    ]
    return r


# ── Registry owns the truth; only its methods change positions ─────────────
def test_registry_add_position_funds_from_cash():
    r = PortfolioRegistry(cash_usd=5_000)
    r.add_position(Position("X", AssetClass.CRYPTO, 2_000))
    assert r.cash_usd == 3_000
    assert r.invested_usd == 2_000
    assert r.total_value_usd == 5_000
    assert r.transactions[-1]["type"] == "buy"


# ── Allocation normalizes everything to USD % ──────────────────────────────
def test_allocation_breakdown_sums_sensibly():
    a = AllocationEngine().allocate(_reg())
    assert a.total_usd == 100_000
    assert a.cash_pct == 0.1
    assert a.by_class[AssetClass.ETF.value] == 0.4
    assert a.by_class[AssetClass.CRYPTO.value] == 0.3
    assert a.by_class[AssetClass.OWN_BUSINESS.value] == 0.2


# ── Diversification: concentration + exposures ─────────────────────────────
def test_diversification_scores_spread_higher_than_concentrated():
    spread = DiversificationEngine().assess(_reg())
    concentrated = PortfolioRegistry()
    concentrated.positions = [Position("BTC", AssetClass.CRYPTO, 100_000, sector="crypto",
                                       meme=True)]
    conc = DiversificationEngine().assess(concentrated)
    assert spread.diversification_score > conc.diversification_score
    assert conc.meme_exposure == 1.0
    assert conc.asset_class_concentration == 1.0


# ── Portfolio risk v2: concentration, liquidity, runway ────────────────────
def test_portfolio_risk_reports_runway_and_concentration():
    rep = PortfolioRiskEngine().assess(_reg(), monthly_burn_usd=2_000)
    assert rep.concentration == 0.4444                    # SPY largest: 40k of 90k invested
    assert 0 < rep.liquidity < 1
    assert rep.cash_runway_months == 5.0                 # 10k cash / 2k burn
    assert 0 <= rep.risk_score <= 100


def test_illiquid_concentrated_portfolio_scores_riskier():
    safe = PortfolioRiskEngine().assess(_reg(), monthly_burn_usd=2_000)
    risky_reg = PortfolioRegistry(cash_usd=1_000)
    risky_reg.positions = [Position("MEME", AssetClass.CRYPTO, 99_000, sector="crypto",
                                    volatility=0.9, liquidity=0.2, meme=True)]
    risky = PortfolioRiskEngine().assess(risky_reg, monthly_burn_usd=2_000)
    assert risky.risk_score < safe.risk_score


# ── Health score: one number, six sub-scores ───────────────────────────────
def test_health_score_in_range_and_composed():
    h = PortfolioHealthScore().compute(_reg(), monthly_burn_usd=2_000)
    assert 0 <= h.overall <= 100
    assert h.risk > 0 and h.diversification > 0
    assert "Health" in h.render()


# ── Rebalancing: recommendations only, off-target flagged, sorted ──────────
def test_rebalancing_flags_offtarget_only():
    actions = RebalancingEngine().recommend(_reg(), targets={
        "cash": 0.1,                                     # on target → no action
        AssetClass.CRYPTO.value: 0.15,                  # at 0.30 → reduce 15%
        AssetClass.ETF.value: 0.40,                     # on target → no action
    })
    targets_hit = {a.target for a in actions}
    assert AssetClass.CRYPTO.value in targets_hit
    assert "cash" not in targets_hit
    assert actions[0].action == "reduce"                 # crypto over-weight


# ── Impact Simulator: evaluates opportunity IN the portfolio, no mutation ──
def test_impact_simulator_does_not_mutate_and_reports_delta():
    reg = _reg()
    before_positions = len(reg.positions)
    before_cash = reg.cash_usd
    new = Position("AI_ETF", AssetClass.ETF, 5_000, sector="ai", volatility=0.2,
                   liquidity=0.9, ai=True)
    report = PortfolioImpactSimulator().simulate(reg, new, monthly_burn_usd=2_000)
    # registry untouched
    assert len(reg.positions) == before_positions
    assert reg.cash_usd == before_cash
    # report is a real before/after comparison
    assert report.after.overall != report.before.overall or report.delta_health == 0.0
    assert isinstance(report.improves, bool)
    assert "Impact" in report.render()


def test_impact_simulator_flags_concentration_increase():
    reg = _reg()
    # dump everything into more of the same volatile crypto sector
    bad = Position("MEME2", AssetClass.CRYPTO, 9_000, sector="crypto", volatility=0.95,
                   liquidity=0.2, meme=True)
    report = PortfolioImpactSimulator().simulate(reg, bad, monthly_burn_usd=2_000)
    assert report.delta_volatility > 0                   # portfolio got more volatile


# ── Capital Reserve Engine: financial vs business, every dollar competes ────
def test_capital_reserve_prefers_best_risk_adjusted_across_kinds():
    engine = CapitalReserveEngine()
    options = [
        ReserveOption("Buy AI coin", ReserveKind.FINANCIAL, expected_return=0.28,
                      risk=0.8, strategic_value=0.4, confidence=0.5,
                      time_to_payoff_months=12, capital_required_usd=5_000),
        ReserveOption("YouTube marketing", ReserveKind.GROWTH, expected_return=0.41,
                      risk=0.3, strategic_value=0.85, confidence=0.8,
                      time_to_payoff_months=3, capital_required_usd=5_000),
        ReserveOption("Kitchen equipment", ReserveKind.BUSINESS, expected_return=0.18,
                      risk=0.15, strategic_value=0.7, confidence=0.9,
                      time_to_payoff_months=6, capital_required_usd=5_000),
    ]
    decision = engine.allocate(5_000, options)
    assert decision.recommended.name == "YouTube marketing"   # best risk-adjusted
    assert decision.ranked[0].score >= decision.ranked[-1].score


def test_capital_reserve_respects_emergency_floor():
    engine = CapitalReserveEngine()
    opt = ReserveOption("Big buy", ReserveKind.FINANCIAL, 0.5, 0.3, 0.6, 0.7, 6,
                        capital_required_usd=8_000)
    with pytest.raises(ValueError):
        engine.allocate(10_000, [opt], emergency_floor_usd=5_000)   # only 5k spendable
