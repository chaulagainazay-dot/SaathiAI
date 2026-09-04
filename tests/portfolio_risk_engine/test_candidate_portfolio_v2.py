"""PORTFOLIO-RISK-V2 atomic CandidatePortfolio hard-limit tests."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from saathi.platform.market_data.contract import AssetClass
from saathi.platform.portfolio_construction.models import (
    CandidatePortfolio,
    CandidatePortfolioStatus,
    InstrumentAllocation,
    PortfolioPosition,
    PortfolioSnapshotInput,
)
from saathi.platform.portfolio_risk_engine import PAPER_BUDGET_V2
from saathi.platform.portfolio_risk_engine.engine import PortfolioRiskEngine
from saathi.platform.portfolio_risk_engine.models import (
    REASON_CANDIDATE_AUTHORITY_INVALID,
    REASON_CANDIDATE_CURRENCY_MISMATCH,
    REASON_CANDIDATE_SNAPSHOT_MISMATCH,
    REASON_CRYPTO_EXPOSURE_LIMIT,
    REASON_MIN_CASH_BUFFER_BREACH,
    REASON_NEPSE_EXPOSURE_LIMIT,
    RiskResult,
)


NOW = datetime(2026, 1, 2, tzinfo=timezone.utc)
BTC = "BINANCE:BTC/USDT"
ETH = "BINANCE:ETH/USDT"


def _snapshot(*, ref: str = "ledger:1", recon: str = "HEALTHY") -> PortfolioSnapshotInput:
    return PortfolioSnapshotInput(
        fund_id="fund-risk-v2",
        snapshot_ref=ref,
        reporting_currency="USDT",
        nav=Decimal("100000"),
        cash=Decimal("100000"),
        available_cash=Decimal("100000"),
        reserved_cash=Decimal("0"),
        unsettled_cash=Decimal("0"),
        positions=(),
        current_drawdown=Decimal("0"),
        source_authority="CANONICAL_FUND_LEDGER",
        reconciliation_status=recon,
    )


def _allocation(
    instrument_id: str = BTC,
    weight: str = "0.10",
    *,
    asset_class: AssetClass = AssetClass.CRYPTO,
    currency: str = "USDT",
) -> InstrumentAllocation:
    value = Decimal(weight)
    return InstrumentAllocation(
        instrument_id=instrument_id,
        symbol="BTCUSDT" if instrument_id == BTC else "ETHUSDT",
        asset_class=asset_class,
        quote_currency=currency,
        current_weight=Decimal("0"),
        target_weight=value,
        weight_change=value,
        target_notional=value * Decimal("100000"),
        estimated_cost=Decimal("40"),
        strategy_ids=("crypto_spot_mean_reversion",),
        intent_ids=("intent:1",),
    )


def _candidate(
    *,
    allocations: tuple[InstrumentAllocation, ...] = (_allocation(),),
    cash_target: str | None = None,
    snapshot_ref: str = "ledger:1",
    quality: str = "VALID_WITH_LIMITATIONS",
    authorizes_execution: bool = False,
    risk_approved: bool = False,
    risk_budget_version: str = PAPER_BUDGET_V2.version,
) -> CandidatePortfolio:
    gross = sum((x.target_weight for x in allocations), Decimal("0"))
    cash = Decimal(cash_target) if cash_target is not None else Decimal("1") - gross
    return CandidatePortfolio(
        candidate_portfolio_id="pcand-risk-v2",
        request_id="pcreq-risk-v2",
        fund_id="fund-risk-v2",
        status=(
            CandidatePortfolioStatus.CANDIDATE_ALLOCATION
            if allocations
            else CandidatePortfolioStatus.ZERO_ALLOCATION
        ),
        portfolio_snapshot_ref=snapshot_ref,
        market_data_snapshot_ref="market:1",
        construction_policy_version="portfolio-construction/v2.0.0-configured-conservative",
        risk_budget_version=risk_budget_version,
        decision_time=NOW,
        allocations=allocations,
        cash_current_weight=Decimal("1"),
        cash_target_weight=cash,
        turnover=gross,
        estimated_cost=sum((x.estimated_cost for x in allocations), Decimal("0")),
        rejected_intents=(),
        constraint_effects=(),
        reason_codes=(),
        intent_ids=("intent:1",) if allocations else (),
        strategy_ids=("crypto_spot_mean_reversion",) if allocations else (),
        qualification_artifact_sha256=("a" * 64,) if allocations else (),
        dataset_versions=("sha256-dataset",) if allocations else (),
        selected_config_hashes=("b" * 64,) if allocations else (),
        policy_assumption_status="CONFIGURED_POLICY_ASSUMPTION",
        quality=quality,
        market_data_mode="HISTORICAL",
        authorizes_execution=authorizes_execution,
        risk_approved=risk_approved,
    )


def _evaluate(candidate: CandidatePortfolio, snapshot: PortfolioSnapshotInput | None = None):
    return PortfolioRiskEngine(budget=PAPER_BUDGET_V2).evaluate_candidate_portfolio(
        candidate,
        portfolio_snapshot=snapshot or _snapshot(),
    )


def test_valid_candidate_is_risk_allowed_but_never_risk_approved_or_executable():
    decision = _evaluate(_candidate())

    assert decision.result == RiskResult.ALLOW
    public = decision.to_public()
    assert public["authorizes_execution"] is False
    assert public["proposal"]["risk_approved"] is False
    assert public["proposal"]["authorizes_execution"] is False
    assert public["projected"]["crypto_exposure"] == "0.10"


@pytest.mark.parametrize("weight", ["0.1501", "-0.01", "1.01"])
def test_invalid_or_overweight_long_only_target_is_blocked(weight):
    decision = _evaluate(_candidate(allocations=(_allocation(weight=weight),)))
    assert decision.result == RiskResult.BLOCK


def test_crypto_sleeve_limit_is_hard_even_when_each_position_is_below_cap():
    candidate = _candidate(
        allocations=(_allocation(BTC, "0.11"), _allocation(ETH, "0.10")),
    )
    decision = _evaluate(candidate)

    assert decision.result == RiskResult.BLOCK
    assert REASON_CRYPTO_EXPOSURE_LIMIT in decision.reason_codes


def test_nepse_candidate_remains_hard_blocked_while_policy_is_unverified():
    allocation = _allocation(
        "NEPSE:NABIL",
        "0.01",
        asset_class=AssetClass.EQUITY,
        currency="USDT",
    )
    decision = _evaluate(_candidate(allocations=(allocation,)))

    assert decision.result == RiskResult.BLOCK
    assert REASON_NEPSE_EXPOSURE_LIMIT in decision.reason_codes


def test_cash_floor_and_funded_weight_identity_are_hard_limits():
    decision = _evaluate(_candidate(cash_target="0.04"))

    assert decision.result == RiskResult.BLOCK
    assert REASON_MIN_CASH_BUFFER_BREACH in decision.reason_codes


def test_candidate_currency_cannot_assume_implicit_fx_conversion():
    decision = _evaluate(_candidate(allocations=(_allocation(currency="USD"),)))

    assert decision.result == RiskResult.BLOCK
    assert REASON_CANDIDATE_CURRENCY_MISMATCH in decision.reason_codes


def test_candidate_snapshot_and_reconciliation_are_bound_fail_closed():
    mismatch = _evaluate(_candidate(snapshot_ref="ledger:other"))
    unreconciled = _evaluate(_candidate(), _snapshot(recon="RECONCILIATION_REQUIRED"))

    assert mismatch.result == RiskResult.BLOCK
    assert REASON_CANDIDATE_SNAPSHOT_MISMATCH in mismatch.reason_codes
    assert unreconciled.result == RiskResult.BLOCK


@pytest.mark.parametrize(
    "candidate",
    [
        _candidate(authorizes_execution=True),
        _candidate(risk_approved=True),
        _candidate(quality="STALE"),
        _candidate(risk_budget_version="wrong-budget"),
    ],
)
def test_candidate_authority_quality_and_policy_mismatches_fail_closed(candidate):
    decision = _evaluate(candidate)

    assert decision.result == RiskResult.BLOCK
    assert REASON_CANDIDATE_AUTHORITY_INVALID in decision.reason_codes


def test_atomic_evaluation_does_not_mutate_candidate_or_snapshot():
    candidate = _candidate()
    snapshot = _snapshot()
    before_candidate = candidate.to_public()
    before_snapshot = snapshot.to_public()

    _evaluate(candidate, snapshot)

    assert candidate.to_public() == before_candidate
    assert snapshot.to_public() == before_snapshot


def test_duplicate_instrument_or_inconsistent_current_cash_is_blocked():
    duplicate = _evaluate(
        _candidate(allocations=(_allocation(BTC, "0.10"), _allocation(BTC, "0.05")))
    )
    bad_cash = _evaluate(replace(_candidate(), cash_current_weight=Decimal("0.50")))
    bad_turnover = _evaluate(replace(_candidate(), turnover=Decimal("0.01")))
    bad_cost = _evaluate(replace(_candidate(), estimated_cost=Decimal("0")))

    assert duplicate.result == RiskResult.BLOCK
    assert bad_cash.result == RiskResult.BLOCK
    assert bad_turnover.result == RiskResult.BLOCK
    assert bad_cost.result == RiskResult.BLOCK
