"""Execution Layer tests (M5 Phase 5) — governed, auditable, idempotent, no bypass.

Deterministic (AP-17); price/clock/publish/record/registry injected (AP-12).
"""
import pytest

from saathi.investment import AssetClass, Verdict
from saathi.opportunity import Opportunity, OpportunityCategory
from saathi.investment_pipeline import InvestmentCase
from saathi.investment import Recommendation, RiskLevel
from saathi.portfolio import PortfolioRegistry
from saathi.execution import (
    ExecutionIntent, ExecutionSide, OrderType, ExecutionStatus,
    PaperConnector, ReplayConnector, BrokerRegistry, ExecutionService,
)

NOW = 5_000_000.0
PRICE = {"BTC": 60_000.0, "SPY": 500.0}


def _price(sym):
    return PRICE[sym]


def _opp(title="BTC", category=OpportunityCategory.INVESTMENT, asset_type="crypto"):
    return Opportunity(title, category, "gh", asset_type, expected_roi=1.5, risk=0.3,
                       strategic_fit=0.8, urgency=0.7, time_horizon_months=12,
                       capital_required_usd=1000, sources=["gh"])


def _approved_case(verdict=Verdict.BUY, approver="ajay"):
    rec = Recommendation(
        opportunity="BTC", verdict=verdict, confidence=0.8, risk_level=RiskLevel.MEDIUM,
        investment_usd=5000, max_allocation_pct=0.05, horizon_months=12,
        evidence_count=6, dd_passed=True, simulation_ev_usd=1000)
    case = InvestmentCase(opportunity=_opp(), recommendation=rec)
    if approver:
        case.approve(approver)
    return case


def _service(portfolio=None, extra=None, events=None, episodes=None):
    reg = BrokerRegistry()
    reg.register(PaperConnector(_price, starting_cash=1_000_000))
    if extra is not None:
        reg.register(extra)
    return ExecutionService(
        reg, portfolio=portfolio,
        publish=lambda n, p: (events if events is not None else []).append((n, p)),
        record_episode=lambda **kw: (episodes if episodes is not None else []).append(kw) or 1)


# ── THE GUARD: no intent without human approval (Governance L4) ─────────────
def test_intent_requires_approved_case():
    unapproved = _approved_case(approver=None)     # BUY but never approved
    assert unapproved.executable is False
    with pytest.raises(PermissionError):
        ExecutionIntent.from_case(unapproved, broker="paper", account="main",
                                  symbol="BTC", quantity=0.1, now=NOW)


def test_rejected_case_can_never_execute():
    rejected = _approved_case(verdict=Verdict.REJECT, approver=None)
    with pytest.raises(PermissionError):
        ExecutionIntent.from_case(rejected, broker="paper", account="main",
                                  symbol="BTC", quantity=0.1, now=NOW)


def test_intent_from_approved_case_carries_audit_fields():
    intent = ExecutionIntent.from_case(_approved_case(), broker="paper", account="main",
                                       symbol="BTC", quantity=0.1, now=NOW)
    assert intent.side is ExecutionSide.BUY
    assert intent.approved_by == "ajay"
    assert intent.asset_class is AssetClass.CRYPTO
    assert intent.expires_at > intent.created_at


# ── Preview before execution ────────────────────────────────────────────────
def test_preview_estimates_cost_fee_and_cash():
    svc = _service()
    intent = ExecutionIntent.from_case(_approved_case(), broker="paper", account="m",
                                       symbol="BTC", quantity=0.1, now=NOW)
    prev = svc.preview(intent, NOW)
    assert prev.estimated_cost_usd > 6000        # 0.1 * 60k + slippage
    assert prev.estimated_fee_usd > 0
    assert "BTC" in prev.render()


# ── Execute requires confirmation; fills update portfolio; emits events ────
def test_execute_requires_confirmation():
    svc = _service()
    intent = ExecutionIntent.from_case(_approved_case(), broker="paper", account="m",
                                       symbol="BTC", quantity=0.1, now=NOW)
    with pytest.raises(PermissionError):
        svc.execute(intent, NOW, confirm=False)


def test_fill_updates_portfolio_and_publishes_and_records():
    events, episodes = [], []
    port = PortfolioRegistry(cash_usd=0)
    svc = _service(portfolio=port, events=events, episodes=episodes)
    intent = ExecutionIntent.from_case(_approved_case(), broker="paper", account="m",
                                       symbol="BTC", quantity=0.1, now=NOW)
    order = svc.execute(intent, NOW)
    assert order.status is ExecutionStatus.FILLED
    assert len(port.positions) == 1 and port.positions[0].symbol == "BTC"
    assert events[0][0] == "execution.filled"
    assert episodes[0]["intent"] == "execute_trade" and episodes[0]["outcome"] == "success"


# ── Expired intent is rejected, never executed ─────────────────────────────
def test_expired_intent_rejected():
    events = []
    svc = _service(events=events)
    intent = ExecutionIntent.from_case(_approved_case(), broker="paper", account="m",
                                       symbol="BTC", quantity=0.1, now=NOW, ttl_s=10)
    order = svc.execute(intent, NOW + 100)       # past expiry
    assert order.status is ExecutionStatus.REJECTED
    assert events[0][0] == "execution.failed"


# ── Idempotency: re-executing the same intent never double-trades ──────────
def test_execute_is_idempotent():
    port = PortfolioRegistry(cash_usd=0)
    reg = BrokerRegistry()
    paper = PaperConnector(_price, starting_cash=1_000_000)
    reg.register(paper)
    svc = ExecutionService(reg, portfolio=port, publish=lambda n, p: None,
                           record_episode=lambda **kw: 1)
    intent = ExecutionIntent.from_case(_approved_case(), broker="paper", account="m",
                                       symbol="BTC", quantity=0.1, now=NOW)
    o1 = svc.execute(intent, NOW)
    o2 = paper.execute(intent, NOW)              # broker re-called with same intent_id
    assert o1.broker_order_id == o2.broker_order_id
    assert len(paper.orders()) == 1              # ONE order, not two


# ── Failure recovery: timeout-after-fill reconciles, never double-trades ───
def test_timeout_after_fill_reconciles_without_duplicate():
    replay = ReplayConnector(_price, script=["timeout_filled"], starting_cash=1_000_000)
    reg = BrokerRegistry()
    reg.register(replay)
    port = PortfolioRegistry(cash_usd=0)
    svc = ExecutionService(reg, portfolio=port, publish=lambda n, p: None,
                           record_episode=lambda **kw: 1)
    intent = ExecutionIntent.from_case(_approved_case(), broker="replay", account="m",
                                       symbol="BTC", quantity=0.1, now=NOW)
    order = svc.execute(intent, NOW)
    assert order.status is ExecutionStatus.FILLED
    assert len(replay.orders()) == 1             # reconciled, not retried into a dup
    assert len(port.positions) == 1


# ── Broker registry selects connector by name; unknown broker errors ───────
def test_broker_registry_selection():
    reg = BrokerRegistry()
    reg.register(PaperConnector(_price))
    assert "paper" in reg.names()
    with pytest.raises(KeyError):
        reg.get("binance")
