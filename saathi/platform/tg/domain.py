"""M166 — Trading Guardian domain model.

Immutable-friendly dataclasses with schema versioning, provenance, and
tenant scope. Decimal-precise money fields. PAPER / research only.
"""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any

from saathi.platform.trading_models import D

SCHEMA_VERSION = "m166.tg.domain.v1"
ENGINE_VERSION = "m166.tg.engine.v1"


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def _now() -> float:
    return time.time()


# ── authority ────────────────────────────────────────────────────────────────
class AuthorityMode(str, Enum):
    """Executable authority levels. LIVE is intentionally absent."""

    ADVISORY = "ADVISORY"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    LIMITED_AUTONOMOUS_PAPER = "LIMITED_AUTONOMOUS_PAPER"


DEFAULT_AUTHORITY_MODE = AuthorityMode.ADVISORY


# ── market regime ────────────────────────────────────────────────────────────
class MarketRegime(str, Enum):
    BULL_TREND = "BULL_TREND"
    BEAR_TREND = "BEAR_TREND"
    SIDEWAYS = "SIDEWAYS"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    LOW_LIQUIDITY = "LOW_LIQUIDITY"
    EVENT_RISK = "EVENT_RISK"
    UNKNOWN = "UNKNOWN"


# ── strategy lifecycle ───────────────────────────────────────────────────────
class StrategyActivation(str, Enum):
    DRAFT = "DRAFT"
    REGISTERED = "REGISTERED"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    DEPRECATED = "DEPRECATED"


class StrategyEvaluationVerdict(str, Enum):
    """Promotion verdicts. LIVE_APPROVED is intentionally absent."""

    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    RESEARCH_ONLY = "RESEARCH_ONLY"
    PAPER_ELIGIBLE = "PAPER_ELIGIBLE"
    PAPER_APPROVAL_REQUIRED = "PAPER_APPROVAL_REQUIRED"
    PAPER_SUSPENDED = "PAPER_SUSPENDED"
    REJECTED = "REJECTED"


class GateStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class ProposalStatus(str, Enum):
    DRAFT = "DRAFT"
    SIGNALED = "SIGNALED"
    POLICY_REVIEW = "POLICY_REVIEW"
    POLICY_BLOCKED = "POLICY_BLOCKED"
    RISK_REVIEW = "RISK_REVIEW"
    RISK_BLOCKED = "RISK_BLOCKED"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    PAPER_SUBMITTED = "PAPER_SUBMITTED"
    PAPER_FILLED = "PAPER_FILLED"
    PAPER_CANCELLED = "PAPER_CANCELLED"
    SUPERSEDED = "SUPERSEDED"


class KillSwitchScope(str, Enum):
    GLOBAL = "GLOBAL"
    STRATEGY = "STRATEGY"
    INSTRUMENT = "INSTRUMENT"
    MARKET = "MARKET"
    WORKSPACE = "WORKSPACE"
    PORTFOLIO = "PORTFOLIO"
    AUTOMATION = "AUTOMATION"
    TRADING_GUARDIAN = "TRADING_GUARDIAN"


# ── helpers ──────────────────────────────────────────────────────────────────
def strategy_fingerprint(payload: dict[str, Any]) -> str:
    """Deterministic fingerprint for a strategy version definition."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ── entities ─────────────────────────────────────────────────────────────────
@dataclass
class StrategyParameterSet:
    schema_version: str = SCHEMA_VERSION
    parameters: dict[str, Any] = field(default_factory=dict)
    parameter_schema: dict[str, Any] = field(default_factory=dict)

    def to_public(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "parameters": self.parameters,
            "parameter_schema": self.parameter_schema,
        }


@dataclass
class StrategyVersion:
    id: str = field(default_factory=lambda: _id("sver"))
    strategy_id: str = ""
    version: str = "1.0.0"
    schema_version: str = SCHEMA_VERSION
    created_at: float = field(default_factory=_now)
    source_identity: str = "system"
    parameters: StrategyParameterSet = field(default_factory=StrategyParameterSet)
    supported_instruments: list[str] = field(default_factory=list)
    supported_timeframes: list[str] = field(default_factory=list)
    required_data_fields: list[str] = field(default_factory=list)
    regime_compatibility: list[str] = field(default_factory=list)
    activation: StrategyActivation = StrategyActivation.DRAFT
    deprecated: bool = False
    fingerprint: str = ""
    reproducibility: dict[str, Any] = field(default_factory=dict)
    assumptions: list[str] = field(default_factory=list)
    invalidation_conditions: list[str] = field(default_factory=list)
    stop_logic: str = ""
    holding_horizon: str = ""
    confidence_components: list[str] = field(default_factory=list)
    immutable: bool = False
    policy_version: str = "1.0.0"
    correlation_id: str = ""
    org_id: str = ""
    workspace_id: str = ""
    project_id: str = ""
    mission_id: str = ""

    def freeze(self) -> None:
        self.immutable = True
        self.activation = StrategyActivation.ACTIVE

    def to_public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "strategy_id": self.strategy_id,
            "version": self.version,
            "schema_version": self.schema_version,
            "created_at": self.created_at,
            "source_identity": self.source_identity,
            "parameters": self.parameters.to_public(),
            "supported_instruments": list(self.supported_instruments),
            "supported_timeframes": list(self.supported_timeframes),
            "required_data_fields": list(self.required_data_fields),
            "regime_compatibility": list(self.regime_compatibility),
            "activation": self.activation.value,
            "deprecated": self.deprecated,
            "fingerprint": self.fingerprint,
            "reproducibility": dict(self.reproducibility),
            "assumptions": list(self.assumptions),
            "invalidation_conditions": list(self.invalidation_conditions),
            "stop_logic": self.stop_logic,
            "holding_horizon": self.holding_horizon,
            "confidence_components": list(self.confidence_components),
            "immutable": self.immutable,
            "policy_version": self.policy_version,
            "correlation_id": self.correlation_id,
            "org_id": self.org_id,
            "workspace_id": self.workspace_id,
            "project_id": self.project_id,
            "mission_id": self.mission_id,
        }


@dataclass
class TradingStrategy:
    id: str = field(default_factory=lambda: _id("strat"))
    schema_version: str = SCHEMA_VERSION
    created_at: float = field(default_factory=_now)
    updated_at: float = field(default_factory=_now)
    name: str = ""
    slug: str = ""
    description: str = ""
    family: str = ""  # mean_reversion | trend | momentum | control
    source_identity: str = "system"
    activation: StrategyActivation = StrategyActivation.DRAFT
    deprecated: bool = False
    latest_version: str = "1.0.0"
    versions: list[StrategyVersion] = field(default_factory=list)
    org_id: str = ""
    workspace_id: str = ""
    project_id: str = ""
    mission_id: str = ""
    evaluation_verdict: StrategyEvaluationVerdict = StrategyEvaluationVerdict.INSUFFICIENT_EVIDENCE
    paper_only: bool = True
    live_authorized: bool = False

    def to_public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "schema_version": self.schema_version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "name": self.name,
            "slug": self.slug,
            "description": self.description,
            "family": self.family,
            "source_identity": self.source_identity,
            "activation": self.activation.value,
            "deprecated": self.deprecated,
            "latest_version": self.latest_version,
            "versions": [v.to_public() for v in self.versions],
            "org_id": self.org_id,
            "workspace_id": self.workspace_id,
            "project_id": self.project_id,
            "mission_id": self.mission_id,
            "evaluation_verdict": self.evaluation_verdict.value,
            "paper_only": True,
            "live_authorized": False,
            "funds_label": "SIMULATED",
        }


@dataclass
class MarketInstrument:
    id: str = field(default_factory=lambda: _id("inst"))
    schema_version: str = SCHEMA_VERSION
    created_at: float = field(default_factory=_now)
    symbol: str = ""
    name: str = ""
    asset_class: str = "EQUITY"
    market: str = "SIM"
    currency: str = "USD"
    min_trade_qty: Decimal = field(default_factory=lambda: Decimal("1"))
    tick_size: Decimal = field(default_factory=lambda: Decimal("0.01"))
    source_identity: str = "fixture"
    correlation_id: str = ""

    def to_public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "schema_version": self.schema_version,
            "created_at": self.created_at,
            "symbol": self.symbol,
            "name": self.name,
            "asset_class": self.asset_class,
            "market": self.market,
            "currency": self.currency,
            "min_trade_qty": str(self.min_trade_qty),
            "tick_size": str(self.tick_size),
            "source_identity": self.source_identity,
            "correlation_id": self.correlation_id,
        }


@dataclass
class MarketBar:
    schema_version: str = SCHEMA_VERSION
    symbol: str = ""
    ts: float = 0.0
    open: Decimal = field(default_factory=lambda: Decimal("0"))
    high: Decimal = field(default_factory=lambda: Decimal("0"))
    low: Decimal = field(default_factory=lambda: Decimal("0"))
    close: Decimal = field(default_factory=lambda: Decimal("0"))
    volume: Decimal = field(default_factory=lambda: Decimal("0"))
    timeframe: str = "1d"
    source_identity: str = "fixture"
    quality: str = "VALID"

    def to_public(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "symbol": self.symbol,
            "ts": self.ts,
            "open": str(self.open),
            "high": str(self.high),
            "low": str(self.low),
            "close": str(self.close),
            "volume": str(self.volume),
            "timeframe": self.timeframe,
            "source_identity": self.source_identity,
            "quality": self.quality,
        }


@dataclass
class MarketSnapshot:
    id: str = field(default_factory=lambda: _id("snap"))
    schema_version: str = SCHEMA_VERSION
    created_at: float = field(default_factory=_now)
    symbol: str = ""
    last_price: Decimal = field(default_factory=lambda: Decimal("0"))
    bid: Decimal = field(default_factory=lambda: Decimal("0"))
    ask: Decimal = field(default_factory=lambda: Decimal("0"))
    spread: Decimal = field(default_factory=lambda: Decimal("0"))
    volume: Decimal = field(default_factory=lambda: Decimal("0"))
    avg_traded_value: Decimal = field(default_factory=lambda: Decimal("0"))
    volatility: Decimal = field(default_factory=lambda: Decimal("0"))
    market_state: str = "OPEN"
    data_quality: str = "VALID"
    freshness_seconds: float = 0.0
    bars: list[MarketBar] = field(default_factory=list)
    source_identity: str = "fixture"
    correlation_id: str = ""
    event_risk: bool = False
    earnings_window: bool = False
    sector: str = ""
    benchmark_return: Decimal = field(default_factory=lambda: Decimal("0"))
    breadth: Decimal = field(default_factory=lambda: Decimal("0.5"))
    gap_pct: Decimal = field(default_factory=lambda: Decimal("0"))

    def to_public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "schema_version": self.schema_version,
            "created_at": self.created_at,
            "symbol": self.symbol,
            "last_price": str(self.last_price),
            "bid": str(self.bid),
            "ask": str(self.ask),
            "spread": str(self.spread),
            "volume": str(self.volume),
            "avg_traded_value": str(self.avg_traded_value),
            "volatility": str(self.volatility),
            "market_state": self.market_state,
            "data_quality": self.data_quality,
            "freshness_seconds": self.freshness_seconds,
            "bars": [b.to_public() for b in self.bars],
            "source_identity": self.source_identity,
            "correlation_id": self.correlation_id,
            "event_risk": self.event_risk,
            "earnings_window": self.earnings_window,
            "sector": self.sector,
            "benchmark_return": str(self.benchmark_return),
            "breadth": str(self.breadth),
            "gap_pct": str(self.gap_pct),
            "funds_label": "SIMULATED",
        }


@dataclass
class TradeSignal:
    id: str = field(default_factory=lambda: _id("sig"))
    schema_version: str = SCHEMA_VERSION
    created_at: float = field(default_factory=_now)
    strategy_id: str = ""
    strategy_version: str = ""
    strategy_fingerprint: str = ""
    symbol: str = ""
    side: str = "BUY"  # BUY | SELL (long-only: SELL closes)
    action: str = "ENTER_LONG"
    confidence: Decimal = field(default_factory=lambda: Decimal("0"))
    confidence_components: dict[str, Any] = field(default_factory=dict)
    inputs: dict[str, Any] = field(default_factory=dict)
    explanation: str = ""
    assumptions: list[str] = field(default_factory=list)
    invalidation: list[str] = field(default_factory=list)
    stop_logic: str = ""
    holding_horizon: str = ""
    regime_labels: list[str] = field(default_factory=list)
    source_identity: str = "strategy"
    correlation_id: str = ""
    policy_version: str = "1.0.0"
    org_id: str = ""
    workspace_id: str = ""

    def to_public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "schema_version": self.schema_version,
            "created_at": self.created_at,
            "strategy_id": self.strategy_id,
            "strategy_version": self.strategy_version,
            "strategy_fingerprint": self.strategy_fingerprint,
            "symbol": self.symbol,
            "side": self.side,
            "action": self.action,
            "confidence": str(self.confidence),
            "confidence_components": dict(self.confidence_components),
            "inputs": dict(self.inputs),
            "explanation": self.explanation,
            "assumptions": list(self.assumptions),
            "invalidation": list(self.invalidation),
            "stop_logic": self.stop_logic,
            "holding_horizon": self.holding_horizon,
            "regime_labels": list(self.regime_labels),
            "source_identity": self.source_identity,
            "correlation_id": self.correlation_id,
            "policy_version": self.policy_version,
            "org_id": self.org_id,
            "workspace_id": self.workspace_id,
            "advisory_only": True,
        }


@dataclass
class TradeProposal:
    id: str = field(default_factory=lambda: _id("prop"))
    schema_version: str = SCHEMA_VERSION
    created_at: float = field(default_factory=_now)
    updated_at: float = field(default_factory=_now)
    signal_id: str = ""
    strategy_id: str = ""
    strategy_version: str = ""
    strategy_fingerprint: str = ""
    policy_version: str = "1.0.0"
    symbol: str = ""
    side: str = "BUY"
    order_type: str = "LIMIT"
    quantity: Decimal = field(default_factory=lambda: Decimal("0"))
    limit_price: Decimal | None = None
    stop_price: Decimal | None = None
    take_profit_price: Decimal | None = None
    entry_price: Decimal = field(default_factory=lambda: Decimal("0"))
    stop_distance: Decimal = field(default_factory=lambda: Decimal("0"))
    reward_to_risk: Decimal = field(default_factory=lambda: Decimal("0"))
    notional: Decimal = field(default_factory=lambda: Decimal("0"))
    status: ProposalStatus = ProposalStatus.DRAFT
    authority_mode: AuthorityMode = AuthorityMode.ADVISORY
    explanation: str = ""
    regime_labels: list[str] = field(default_factory=list)
    market_snapshot_id: str = ""
    market_snapshot: dict[str, Any] = field(default_factory=dict)
    policy_decision_id: str = ""
    risk_decision_id: str = ""
    approval_id: str = ""
    paper_order_id: str = ""
    idempotency_key: str = ""
    expires_at: float = 0.0
    source_identity: str = "strategy"
    correlation_id: str = ""
    org_id: str = ""
    workspace_id: str = ""
    project_id: str = ""
    mission_id: str = ""
    portfolio_id: str = ""
    sector: str = ""
    paper_only: bool = True
    funds_label: str = "SIMULATED"
    live_order: bool = False

    def to_public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "schema_version": self.schema_version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "signal_id": self.signal_id,
            "strategy_id": self.strategy_id,
            "strategy_version": self.strategy_version,
            "strategy_fingerprint": self.strategy_fingerprint,
            "policy_version": self.policy_version,
            "symbol": self.symbol,
            "side": self.side,
            "order_type": self.order_type,
            "quantity": str(self.quantity),
            "limit_price": str(self.limit_price) if self.limit_price is not None else None,
            "stop_price": str(self.stop_price) if self.stop_price is not None else None,
            "take_profit_price": str(self.take_profit_price) if self.take_profit_price is not None else None,
            "entry_price": str(self.entry_price),
            "stop_distance": str(self.stop_distance),
            "reward_to_risk": str(self.reward_to_risk),
            "notional": str(self.notional),
            "status": self.status.value,
            "authority_mode": self.authority_mode.value,
            "explanation": self.explanation,
            "regime_labels": list(self.regime_labels),
            "market_snapshot_id": self.market_snapshot_id,
            "policy_decision_id": self.policy_decision_id,
            "risk_decision_id": self.risk_decision_id,
            "approval_id": self.approval_id,
            "paper_order_id": self.paper_order_id,
            "idempotency_key": self.idempotency_key,
            "expires_at": self.expires_at,
            "source_identity": self.source_identity,
            "correlation_id": self.correlation_id,
            "org_id": self.org_id,
            "workspace_id": self.workspace_id,
            "project_id": self.project_id,
            "mission_id": self.mission_id,
            "portfolio_id": self.portfolio_id,
            "sector": self.sector,
            "paper_only": True,
            "funds_label": "SIMULATED",
            "live_order": False,
            "disclaimer": "PAPER TRADING ONLY — NO LIVE ORDERS — SIMULATED FUNDS",
        }


@dataclass
class PolicyGateResult:
    gate: str
    status: GateStatus
    reason_code: str
    explanation: str
    evidence: dict[str, Any] = field(default_factory=dict)
    policy_version: str = "1.0.0"
    timestamp: float = field(default_factory=_now)

    def to_public(self) -> dict[str, Any]:
        return {
            "gate": self.gate,
            "status": self.status.value,
            "reason_code": self.reason_code,
            "explanation": self.explanation,
            "evidence": dict(self.evidence),
            "policy_version": self.policy_version,
            "timestamp": self.timestamp,
        }


@dataclass
class PolicyDecision:
    id: str = field(default_factory=lambda: _id("pol"))
    schema_version: str = SCHEMA_VERSION
    created_at: float = field(default_factory=_now)
    proposal_id: str = ""
    policy_version: str = "1.0.0"
    allowed: bool = False
    gates: list[PolicyGateResult] = field(default_factory=list)
    source_identity: str = "policy_engine"
    correlation_id: str = ""
    strategy_version: str = ""
    org_id: str = ""
    workspace_id: str = ""

    def to_public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "schema_version": self.schema_version,
            "created_at": self.created_at,
            "proposal_id": self.proposal_id,
            "policy_version": self.policy_version,
            "allowed": self.allowed,
            "gates": [g.to_public() for g in self.gates],
            "source_identity": self.source_identity,
            "correlation_id": self.correlation_id,
            "strategy_version": self.strategy_version,
            "org_id": self.org_id,
            "workspace_id": self.workspace_id,
            "failed_gates": [g.gate for g in self.gates if g.status == GateStatus.FAIL],
        }


@dataclass
class RiskDecision:
    id: str = field(default_factory=lambda: _id("risk"))
    schema_version: str = SCHEMA_VERSION
    created_at: float = field(default_factory=_now)
    proposal_id: str = ""
    allowed: bool = False
    reasons: list[str] = field(default_factory=list)
    checks: list[dict[str, Any]] = field(default_factory=list)
    position_size: Decimal = field(default_factory=lambda: Decimal("0"))
    risk_amount: Decimal = field(default_factory=lambda: Decimal("0"))
    max_loss: Decimal = field(default_factory=lambda: Decimal("0"))
    portfolio_heat: Decimal = field(default_factory=lambda: Decimal("0"))
    sizing_method: str = "FIXED_FRACTIONAL"
    policy_version: str = "1.0.0"
    strategy_version: str = ""
    source_identity: str = "risk_engine"
    correlation_id: str = ""
    org_id: str = ""
    workspace_id: str = ""
    leverage_used: bool = False
    margin_used: bool = False

    def to_public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "schema_version": self.schema_version,
            "created_at": self.created_at,
            "proposal_id": self.proposal_id,
            "allowed": self.allowed,
            "reasons": list(self.reasons),
            "checks": list(self.checks),
            "position_size": str(self.position_size),
            "risk_amount": str(self.risk_amount),
            "max_loss": str(self.max_loss),
            "portfolio_heat": str(self.portfolio_heat),
            "sizing_method": self.sizing_method,
            "policy_version": self.policy_version,
            "strategy_version": self.strategy_version,
            "source_identity": self.source_identity,
            "correlation_id": self.correlation_id,
            "org_id": self.org_id,
            "workspace_id": self.workspace_id,
            "leverage_used": False,
            "margin_used": False,
            "deterministic": True,
            "llm_override": False,
        }


@dataclass
class PaperOrderRef:
    id: str = ""
    proposal_id: str = ""
    strategy_version: str = ""
    policy_decision_id: str = ""
    risk_decision_id: str = ""
    approval_id: str = ""
    execution_trace: str = ""
    market_snapshot_id: str = ""
    paper_broker_config: str = "paper_only_v1"
    status: str = ""
    funds_label: str = "SIMULATED"

    def to_public(self) -> dict[str, Any]:
        return asdict(self) | {"paper_only": True, "live_order": False}


@dataclass
class PaperFillRef:
    id: str = ""
    order_id: str = ""
    quantity: Decimal = field(default_factory=lambda: Decimal("0"))
    price: Decimal = field(default_factory=lambda: Decimal("0"))
    fee: Decimal = field(default_factory=lambda: Decimal("0"))
    slippage: Decimal = field(default_factory=lambda: Decimal("0"))
    ts: float = 0.0
    funds_label: str = "SIMULATED"

    def to_public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "order_id": self.order_id,
            "quantity": str(self.quantity),
            "price": str(self.price),
            "fee": str(self.fee),
            "slippage": str(self.slippage),
            "ts": self.ts,
            "funds_label": "SIMULATED",
            "paper_only": True,
        }


@dataclass
class PaperPositionView:
    symbol: str = ""
    quantity: Decimal = field(default_factory=lambda: Decimal("0"))
    avg_cost: Decimal = field(default_factory=lambda: Decimal("0"))
    market_value: Decimal = field(default_factory=lambda: Decimal("0"))
    unrealized_pnl: Decimal = field(default_factory=lambda: Decimal("0"))
    funds_label: str = "SIMULATED"

    def to_public(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "quantity": str(self.quantity),
            "avg_cost": str(self.avg_cost),
            "market_value": str(self.market_value),
            "unrealized_pnl": str(self.unrealized_pnl),
            "funds_label": "SIMULATED",
            "paper_only": True,
        }


@dataclass
class PaperPortfolioView:
    id: str = field(default_factory=lambda: _id("pf"))
    schema_version: str = SCHEMA_VERSION
    cash: Decimal = field(default_factory=lambda: Decimal("0"))
    equity: Decimal = field(default_factory=lambda: Decimal("0"))
    reserved: Decimal = field(default_factory=lambda: Decimal("0"))
    realized_pnl: Decimal = field(default_factory=lambda: Decimal("0"))
    unrealized_pnl: Decimal = field(default_factory=lambda: Decimal("0"))
    positions: list[PaperPositionView] = field(default_factory=list)
    funds_label: str = "SIMULATED"
    paper_only: bool = True
    org_id: str = ""
    workspace_id: str = ""

    def to_public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "schema_version": self.schema_version,
            "cash": str(self.cash),
            "equity": str(self.equity),
            "reserved": str(self.reserved),
            "realized_pnl": str(self.realized_pnl),
            "unrealized_pnl": str(self.unrealized_pnl),
            "positions": [p.to_public() for p in self.positions],
            "funds_label": "SIMULATED",
            "paper_only": True,
            "live_money": False,
            "disclaimer": "SIMULATED FUNDS — NOT REAL MONEY",
            "org_id": self.org_id,
            "workspace_id": self.workspace_id,
        }


@dataclass
class TradeJournalEntry:
    id: str = field(default_factory=lambda: _id("jnl"))
    schema_version: str = SCHEMA_VERSION
    created_at: float = field(default_factory=_now)
    proposal_id: str = ""
    strategy_id: str = ""
    strategy_version: str = ""
    regime: list[str] = field(default_factory=list)
    signal: dict[str, Any] = field(default_factory=dict)
    proposal: dict[str, Any] = field(default_factory=dict)
    policy_gates: list[dict[str, Any]] = field(default_factory=list)
    risk_calculation: dict[str, Any] = field(default_factory=dict)
    approval: dict[str, Any] = field(default_factory=dict)
    order: dict[str, Any] = field(default_factory=dict)
    fills: list[dict[str, Any]] = field(default_factory=list)
    stop_target: dict[str, Any] = field(default_factory=dict)
    exit_reason: str = ""
    pnl: Decimal = field(default_factory=lambda: Decimal("0"))
    fees: Decimal = field(default_factory=lambda: Decimal("0"))
    slippage: Decimal = field(default_factory=lambda: Decimal("0"))
    rule_violations: list[str] = field(default_factory=list)
    operator_notes: str = ""
    evidence_refs: list[str] = field(default_factory=list)
    market_context: dict[str, Any] = field(default_factory=dict)
    correlation_id: str = ""
    source_identity: str = "journal"
    policy_version: str = "1.0.0"
    org_id: str = ""
    workspace_id: str = ""
    immutable: bool = True
    funds_label: str = "SIMULATED"

    def to_public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "schema_version": self.schema_version,
            "created_at": self.created_at,
            "proposal_id": self.proposal_id,
            "strategy_id": self.strategy_id,
            "strategy_version": self.strategy_version,
            "regime": list(self.regime),
            "signal": dict(self.signal),
            "proposal": dict(self.proposal),
            "policy_gates": list(self.policy_gates),
            "risk_calculation": dict(self.risk_calculation),
            "approval": dict(self.approval),
            "order": dict(self.order),
            "fills": list(self.fills),
            "stop_target": dict(self.stop_target),
            "exit_reason": self.exit_reason,
            "pnl": str(self.pnl),
            "fees": str(self.fees),
            "slippage": str(self.slippage),
            "rule_violations": list(self.rule_violations),
            "operator_notes": self.operator_notes,
            "evidence_refs": list(self.evidence_refs),
            "market_context": dict(self.market_context),
            "correlation_id": self.correlation_id,
            "source_identity": self.source_identity,
            "policy_version": self.policy_version,
            "org_id": self.org_id,
            "workspace_id": self.workspace_id,
            "immutable": True,
            "funds_label": "SIMULATED",
            "paper_only": True,
        }


@dataclass
class PerformanceMetrics:
    schema_version: str = SCHEMA_VERSION
    total_return: Decimal = field(default_factory=lambda: Decimal("0"))
    annualized_return: Decimal | None = None
    benchmark_return: Decimal = field(default_factory=lambda: Decimal("0"))
    excess_return: Decimal = field(default_factory=lambda: Decimal("0"))
    max_drawdown: Decimal = field(default_factory=lambda: Decimal("0"))
    volatility: Decimal = field(default_factory=lambda: Decimal("0"))
    sharpe: Decimal | None = None
    sortino: Decimal | None = None
    calmar: Decimal | None = None
    win_rate: Decimal = field(default_factory=lambda: Decimal("0"))
    loss_rate: Decimal = field(default_factory=lambda: Decimal("0"))
    profit_factor: Decimal | None = None
    expectancy: Decimal = field(default_factory=lambda: Decimal("0"))
    avg_win: Decimal = field(default_factory=lambda: Decimal("0"))
    avg_loss: Decimal = field(default_factory=lambda: Decimal("0"))
    payoff_ratio: Decimal | None = None
    largest_win: Decimal = field(default_factory=lambda: Decimal("0"))
    largest_loss: Decimal = field(default_factory=lambda: Decimal("0"))
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0
    number_of_trades: int = 0
    exposure_time: Decimal = field(default_factory=lambda: Decimal("0"))
    turnover: Decimal = field(default_factory=lambda: Decimal("0"))
    estimated_fees: Decimal = field(default_factory=lambda: Decimal("0"))
    estimated_slippage: Decimal = field(default_factory=lambda: Decimal("0"))
    rejected_trade_count: int = 0
    policy_blocked_count: int = 0
    split_kind: str = "IN_SAMPLE"  # IN_SAMPLE | VALIDATION | OUT_OF_SAMPLE | WALK_FORWARD

    def to_public(self) -> dict[str, Any]:
        def s(v: Decimal | None) -> str | None:
            return None if v is None else str(v)

        return {
            "schema_version": self.schema_version,
            "total_return": str(self.total_return),
            "annualized_return": s(self.annualized_return),
            "benchmark_return": str(self.benchmark_return),
            "excess_return": str(self.excess_return),
            "max_drawdown": str(self.max_drawdown),
            "volatility": str(self.volatility),
            "sharpe": s(self.sharpe),
            "sortino": s(self.sortino),
            "calmar": s(self.calmar),
            "win_rate": str(self.win_rate),
            "loss_rate": str(self.loss_rate),
            "profit_factor": s(self.profit_factor),
            "expectancy": str(self.expectancy),
            "avg_win": str(self.avg_win),
            "avg_loss": str(self.avg_loss),
            "payoff_ratio": s(self.payoff_ratio),
            "largest_win": str(self.largest_win),
            "largest_loss": str(self.largest_loss),
            "max_consecutive_wins": self.max_consecutive_wins,
            "max_consecutive_losses": self.max_consecutive_losses,
            "number_of_trades": self.number_of_trades,
            "exposure_time": str(self.exposure_time),
            "turnover": str(self.turnover),
            "estimated_fees": str(self.estimated_fees),
            "estimated_slippage": str(self.estimated_slippage),
            "rejected_trade_count": self.rejected_trade_count,
            "policy_blocked_count": self.policy_blocked_count,
            "split_kind": self.split_kind,
            "disclaimer": "Historical/simulated metrics are not future performance.",
        }


@dataclass
class BacktestRunRef:
    id: str = field(default_factory=lambda: _id("bt"))
    schema_version: str = SCHEMA_VERSION
    created_at: float = field(default_factory=_now)
    strategy_id: str = ""
    strategy_version: str = ""
    dataset: str = ""
    status: str = "DRAFT"
    seed: int = 0
    cost_tier: str = "realistic"
    split_kind: str = "IN_SAMPLE"
    correlation_id: str = ""
    policy_version: str = "1.0.0"
    org_id: str = ""
    workspace_id: str = ""
    paper_only: bool = True

    def to_public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "schema_version": self.schema_version,
            "created_at": self.created_at,
            "strategy_id": self.strategy_id,
            "strategy_version": self.strategy_version,
            "dataset": self.dataset,
            "status": self.status,
            "seed": self.seed,
            "cost_tier": self.cost_tier,
            "split_kind": self.split_kind,
            "correlation_id": self.correlation_id,
            "policy_version": self.policy_version,
            "org_id": self.org_id,
            "workspace_id": self.workspace_id,
            "paper_only": True,
            "live_authorized": False,
            "disclaimer": "Backtest is research simulation only. Not investment advice.",
        }


@dataclass
class BacktestResultView:
    run: BacktestRunRef = field(default_factory=BacktestRunRef)
    metrics: PerformanceMetrics = field(default_factory=PerformanceMetrics)
    quality: dict[str, Any] = field(default_factory=dict)
    limitations: list[str] = field(default_factory=list)

    def to_public(self) -> dict[str, Any]:
        return {
            "run": self.run.to_public(),
            "metrics": self.metrics.to_public(),
            "quality": dict(self.quality),
            "limitations": list(self.limitations) or [
                "No look-ahead guarantees only within engine safeguards.",
                "Simulated fills may differ from real execution.",
                "Historical performance is not future performance.",
                "No profitability claim.",
            ],
            "paper_only": True,
            "live_authorized": False,
        }


@dataclass
class TradingGuardianPolicy:
    id: str = field(default_factory=lambda: _id("tgpol"))
    schema_version: str = SCHEMA_VERSION
    version: str = "1.0.0"
    created_at: float = field(default_factory=_now)
    updated_at: float = field(default_factory=_now)
    name: str = "default_paper_policy"
    authority_mode: AuthorityMode = AuthorityMode.ADVISORY
    instrument_allowlist: list[str] = field(default_factory=list)
    supported_markets: list[str] = field(default_factory=lambda: ["SIM", "PAPER"])
    supported_timeframes: list[str] = field(default_factory=lambda: ["1d", "1h", "15m"])
    max_data_freshness_seconds: float = 300.0
    max_spread: Decimal = field(default_factory=lambda: Decimal("0.05"))
    min_avg_traded_value: Decimal = field(default_factory=lambda: Decimal("10000"))
    max_volatility: Decimal = field(default_factory=lambda: Decimal("0.08"))
    min_reward_to_risk: Decimal = field(default_factory=lambda: Decimal("1.5"))
    max_open_positions: int = 5
    max_sector_exposure_pct: Decimal = field(default_factory=lambda: Decimal("40"))
    max_correlated_exposure_pct: Decimal = field(default_factory=lambda: Decimal("50"))
    max_portfolio_heat_pct: Decimal = field(default_factory=lambda: Decimal("6"))
    max_risk_per_trade_pct: Decimal = field(default_factory=lambda: Decimal("1"))
    max_position_value: Decimal = field(default_factory=lambda: Decimal("25000"))
    daily_loss_limit: Decimal = field(default_factory=lambda: Decimal("500"))
    weekly_loss_limit: Decimal = field(default_factory=lambda: Decimal("1500"))
    max_drawdown_pct: Decimal = field(default_factory=lambda: Decimal("15"))
    max_consecutive_losses: int = 3
    cooldown_after_losses_seconds: float = 86400.0
    proposal_ttl_seconds: float = 900.0
    require_stop_loss: bool = True
    require_exit_plan: bool = True
    require_approval: bool = True
    allow_event_risk: bool = False
    allow_earnings_window: bool = False
    leverage_allowed: bool = False
    margin_allowed: bool = False
    shorting_allowed: bool = False
    averaging_down_allowed: bool = False
    martingale_allowed: bool = False
    live_trading_allowed: bool = False
    source_identity: str = "system"
    org_id: str = ""
    workspace_id: str = ""

    def to_public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "schema_version": self.schema_version,
            "version": self.version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "name": self.name,
            "authority_mode": self.authority_mode.value,
            "instrument_allowlist": list(self.instrument_allowlist),
            "supported_markets": list(self.supported_markets),
            "supported_timeframes": list(self.supported_timeframes),
            "max_data_freshness_seconds": self.max_data_freshness_seconds,
            "max_spread": str(self.max_spread),
            "min_avg_traded_value": str(self.min_avg_traded_value),
            "max_volatility": str(self.max_volatility),
            "min_reward_to_risk": str(self.min_reward_to_risk),
            "max_open_positions": self.max_open_positions,
            "max_sector_exposure_pct": str(self.max_sector_exposure_pct),
            "max_correlated_exposure_pct": str(self.max_correlated_exposure_pct),
            "max_portfolio_heat_pct": str(self.max_portfolio_heat_pct),
            "max_risk_per_trade_pct": str(self.max_risk_per_trade_pct),
            "max_position_value": str(self.max_position_value),
            "daily_loss_limit": str(self.daily_loss_limit),
            "weekly_loss_limit": str(self.weekly_loss_limit),
            "max_drawdown_pct": str(self.max_drawdown_pct),
            "max_consecutive_losses": self.max_consecutive_losses,
            "cooldown_after_losses_seconds": self.cooldown_after_losses_seconds,
            "proposal_ttl_seconds": self.proposal_ttl_seconds,
            "require_stop_loss": self.require_stop_loss,
            "require_exit_plan": self.require_exit_plan,
            "require_approval": self.require_approval,
            "allow_event_risk": self.allow_event_risk,
            "allow_earnings_window": self.allow_earnings_window,
            "leverage_allowed": False,
            "margin_allowed": False,
            "shorting_allowed": False,
            "averaging_down_allowed": self.averaging_down_allowed,
            "martingale_allowed": False,
            "live_trading_allowed": False,
            "source_identity": self.source_identity,
            "org_id": self.org_id,
            "workspace_id": self.workspace_id,
            "paper_only": True,
        }


@dataclass
class TradingGuardianKillSwitch:
    id: str = field(default_factory=lambda: _id("ks"))
    schema_version: str = SCHEMA_VERSION
    created_at: float = field(default_factory=_now)
    updated_at: float = field(default_factory=_now)
    scope: KillSwitchScope = KillSwitchScope.GLOBAL
    scope_ref: str = ""
    active: bool = False
    reason: str = ""
    activated_by: str = ""
    source_identity: str = "operator"
    correlation_id: str = ""
    org_id: str = ""
    workspace_id: str = ""
    cannot_be_overridden_by_strategy: bool = True
    cannot_be_overridden_by_llm: bool = True

    def to_public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "schema_version": self.schema_version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "scope": self.scope.value,
            "scope_ref": self.scope_ref,
            "active": self.active,
            "reason": self.reason,
            "activated_by": self.activated_by,
            "source_identity": self.source_identity,
            "correlation_id": self.correlation_id,
            "org_id": self.org_id,
            "workspace_id": self.workspace_id,
            "cannot_be_overridden_by_strategy": True,
            "cannot_be_overridden_by_llm": True,
            "immediate": True,
            "persistent": True,
        }


def coerce_decimal(value: Any, default: str = "0") -> Decimal:
    try:
        return D(value, default)
    except Exception:
        return Decimal(default)
