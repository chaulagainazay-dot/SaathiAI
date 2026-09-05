"""Proposal domain models and reason codes."""
from __future__ import annotations

import time as _time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from hashlib import sha256
import json
from typing import Any

from saathi.platform.fund_ledger.money import D, q_money, q_price, q_qty
from saathi.platform.market_data.contract import AssetClass, HistoricalBar
from saathi.platform.signal import TradingIntentProposal


class ProposalStatus(str, Enum):
    DRAFT = "DRAFT"
    READY_FOR_RISK = "READY_FOR_RISK"
    DATA_INSUFFICIENT = "DATA_INSUFFICIENT"
    RISK_BLOCKED = "RISK_BLOCKED"
    RISK_WARN = "RISK_WARN"
    READY_FOR_APPROVAL = "READY_FOR_APPROVAL"
    APPROVED = "APPROVED"  # set by approval system only — engine never auto-sets
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    SUPERSEDED = "SUPERSEDED"
    STALE_PROPOSAL = "STALE_PROPOSAL"


class RebalanceAction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    NO_ACTION = "NO_ACTION"


class ConstructionMethod(str, Enum):
    EQUAL_WEIGHT = "equal_weight"
    FIXED_TARGET = "fixed_target"
    SIGNAL_PROPORTIONAL = "signal_proportional"
    RISK_BUDGET_CONSTRAINED = "risk_budget_constrained"


class UniverseStatus(str, Enum):
    ELIGIBLE = "eligible"
    EXCLUDED = "excluded"
    RESTRICTED = "restricted"
    DATA_INSUFFICIENT = "data_insufficient"


class StrategyQualificationStatus(str, Enum):
    PAPER_CANDIDATE = "PAPER_CANDIDATE"
    OOS_VALIDATED_WITH_LIMITATIONS = "OOS_VALIDATED_WITH_LIMITATIONS"
    RESEARCH_ONLY = "RESEARCH_ONLY"
    REJECTED = "REJECTED"


class CandidatePortfolioStatus(str, Enum):
    ZERO_ALLOCATION = "ZERO_ALLOCATION"
    REDUCED_ALLOCATION = "REDUCED_ALLOCATION"
    CANDIDATE_ALLOCATION = "CANDIDATE_ALLOCATION"


class ConstructionReasonCode(str, Enum):
    STRATEGY_NOT_ELIGIBLE = "STRATEGY_NOT_ELIGIBLE"
    POSITION_CAP = "POSITION_CAP"
    CRYPTO_SLEEVE_CAP = "CRYPTO_SLEEVE_CAP"
    NEPSE_SLEEVE_DISABLED = "NEPSE_SLEEVE_DISABLED"
    CASH_FLOOR = "CASH_FLOOR"
    VOLATILITY_REDUCTION = "VOLATILITY_REDUCTION"
    VOLATILITY_DATA_INSUFFICIENT = "VOLATILITY_DATA_INSUFFICIENT"
    DRAWDOWN_REDUCTION = "DRAWDOWN_REDUCTION"
    CORRELATION_CONCENTRATION = "CORRELATION_CONCENTRATION"
    CORRELATION_DATA_INSUFFICIENT = "CORRELATION_DATA_INSUFFICIENT"
    LIQUIDITY_LIMIT = "LIQUIDITY_LIMIT"
    LIQUIDITY_DATA_INSUFFICIENT = "LIQUIDITY_DATA_INSUFFICIENT"
    CURRENT_POSITION_AT_CAP = "CURRENT_POSITION_AT_CAP"
    CONFLICTING_INTENTS = "CONFLICTING_INTENTS"
    DATA_QUALITY_INSUFFICIENT = "DATA_QUALITY_INSUFFICIENT"
    COST_INEFFICIENT_REBALANCE = "COST_INEFFICIENT_REBALANCE"
    CURRENCY_MISMATCH = "CURRENCY_MISMATCH"
    INSTRUMENT_DISABLED = "INSTRUMENT_DISABLED"
    VENUE_DISABLED = "VENUE_DISABLED"
    EXPIRED_INTENT = "EXPIRED_INTENT"
    FUTURE_DATA_EXCLUDED = "FUTURE_DATA_EXCLUDED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
    UNSUPPORTED_MARKET = "UNSUPPORTED_MARKET"


@dataclass(frozen=True)
class PortfolioPosition:
    instrument_id: str
    symbol: str
    asset_class: AssetClass
    quote_currency: str
    quantity: Decimal
    mark_price: Decimal
    market_value: Decimal

    def __post_init__(self) -> None:
        if not self.instrument_id or self.quantity < 0 or self.mark_price <= 0 or self.market_value < 0:
            raise ValueError("long-only portfolio position must have valid identity and non-negative value")

    def to_public(self) -> dict[str, str]:
        return {
            "instrument_id": self.instrument_id,
            "symbol": self.symbol,
            "asset_class": self.asset_class.value,
            "quote_currency": self.quote_currency,
            "quantity": str(self.quantity),
            "mark_price": str(self.mark_price),
            "market_value": str(self.market_value),
        }


@dataclass(frozen=True)
class PortfolioSnapshotInput:
    fund_id: str
    snapshot_ref: str
    reporting_currency: str
    nav: Decimal
    cash: Decimal
    available_cash: Decimal
    reserved_cash: Decimal
    unsettled_cash: Decimal
    positions: tuple[PortfolioPosition, ...] = ()
    current_drawdown: Decimal = Decimal("0")
    source_authority: str = "CANONICAL_FUND_LEDGER"
    reconciliation_status: str = "UNKNOWN"

    @classmethod
    def from_ledger_view(
        cls,
        view: dict[str, Any],
        *,
        instrument_metadata: tuple["InstrumentMetadata", ...] | list["InstrumentMetadata"],
        snapshot_ref: str,
        current_drawdown: Decimal = Decimal("0"),
        reconciliation_status: str = "UNKNOWN",
    ) -> "PortfolioSnapshotInput":
        """Adapt the canonical fund-ledger view without inventing cash.

        The adapter accepts only the output shape of
        ``LedgerPortfolioViewAdapter``. Raw broker/account objects are not a
        supported source of portfolio truth.
        """
        if view.get("books_authority") != "canonical_fund_ledger":
            raise ValueError("portfolio snapshot must come from canonical fund ledger")
        if view.get("invariants_ok") is not True:
            raise ValueError("canonical fund ledger invariants are not satisfied")
        metadata = {m.instrument_id: m for m in instrument_metadata}
        positions: list[PortfolioPosition] = []
        for row in view.get("positions") or ():
            instrument_id = str(row.get("security_id") or "")
            meta = metadata.get(instrument_id)
            if meta is None:
                raise ValueError(f"instrument metadata missing for ledger position {instrument_id}")
            if row.get("mark_stale"):
                raise ValueError(f"ledger position mark is stale for {instrument_id}")
            quantity = D(row.get("quantity"))
            market_value = D(row.get("market_value"))
            if quantity <= 0 and market_value == 0:
                continue
            if quantity <= 0 or market_value < 0:
                raise ValueError(f"invalid ledger position for {instrument_id}")
            positions.append(
                PortfolioPosition(
                    instrument_id=instrument_id,
                    symbol=str(row.get("symbol") or meta.symbol),
                    asset_class=meta.asset_class,
                    quote_currency=meta.quote_currency,
                    quantity=quantity,
                    mark_price=market_value / quantity,
                    market_value=market_value,
                )
            )
        return cls(
            fund_id=str(view.get("fund_id") or ""),
            snapshot_ref=snapshot_ref,
            reporting_currency=str(view.get("currency") or ""),
            nav=D(view.get("nav")),
            cash=D(view.get("cash")),
            available_cash=D(view.get("available_cash")),
            reserved_cash=D(view.get("reserved_cash")),
            unsettled_cash=D(view.get("unsettled_cash")),
            positions=tuple(sorted(positions, key=lambda p: p.instrument_id)),
            current_drawdown=D(current_drawdown),
            source_authority="CANONICAL_FUND_LEDGER",
            reconciliation_status=reconciliation_status,
        )

    def __post_init__(self) -> None:
        if not self.fund_id or not self.snapshot_ref or self.nav <= 0:
            raise ValueError("fund identity, snapshot reference, and positive NAV are required")
        if any(x < 0 for x in (self.cash, self.available_cash, self.reserved_cash, self.unsettled_cash)):
            raise ValueError("cash components must be non-negative")
        if self.available_cash > self.cash:
            raise ValueError("available cash cannot exceed ledger cash")
        if self.available_cash + self.reserved_cash > self.cash:
            raise ValueError("available and reserved cash cannot exceed ledger cash")
        if not Decimal("0") <= self.current_drawdown <= Decimal("1"):
            raise ValueError("current drawdown must be in [0, 1]")
        ids = [p.instrument_id for p in self.positions]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate portfolio position identity")

    def to_public(self) -> dict[str, Any]:
        return {
            "fund_id": self.fund_id,
            "snapshot_ref": self.snapshot_ref,
            "reporting_currency": self.reporting_currency,
            "nav": str(self.nav),
            "cash": str(self.cash),
            "available_cash": str(self.available_cash),
            "reserved_cash": str(self.reserved_cash),
            "unsettled_cash": str(self.unsettled_cash),
            "positions": [p.to_public() for p in sorted(self.positions, key=lambda p: p.instrument_id)],
            "current_drawdown": str(self.current_drawdown),
            "source_authority": self.source_authority,
            "reconciliation_status": self.reconciliation_status,
        }


@dataclass(frozen=True)
class InstrumentMetadata:
    instrument_id: str
    symbol: str
    venue: str
    asset_class: AssetClass
    quote_currency: str
    market_type: str = "SPOT"
    enabled: bool = True
    venue_enabled: bool = True
    liquidity_limit_weight: Decimal | None = None
    estimated_round_trip_cost_bps: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        if not self.instrument_id or not self.symbol or not self.venue:
            raise ValueError("instrument identity is required")
        if self.liquidity_limit_weight is not None and not Decimal("0") <= self.liquidity_limit_weight <= 1:
            raise ValueError("liquidity limit weight must be in [0, 1]")
        if self.estimated_round_trip_cost_bps < 0:
            raise ValueError("estimated costs must not be negative")

    def to_public(self) -> dict[str, Any]:
        return {
            "instrument_id": self.instrument_id,
            "symbol": self.symbol,
            "venue": self.venue,
            "asset_class": self.asset_class.value,
            "quote_currency": self.quote_currency,
            "market_type": self.market_type,
            "enabled": self.enabled,
            "venue_enabled": self.venue_enabled,
            "liquidity_limit_weight": (
                str(self.liquidity_limit_weight) if self.liquidity_limit_weight is not None else None
            ),
            "estimated_round_trip_cost_bps": str(self.estimated_round_trip_cost_bps),
        }


@dataclass(frozen=True)
class StrategyQualificationEvidence:
    intent_id: str
    signal_ref: str
    strategy_id: str
    strategy_version: str
    instrument_id: str
    status: StrategyQualificationStatus
    qualification_artifact_sha256: str
    dataset_version: str
    selected_config_hash: str
    quality: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", StrategyQualificationStatus(self.status))
        if not all(
            (
                self.intent_id,
                self.signal_ref,
                self.strategy_id,
                self.strategy_version,
                self.instrument_id,
                self.qualification_artifact_sha256,
                self.dataset_version,
                self.selected_config_hash,
            )
        ):
            raise ValueError("immutable qualification references are required")

    def to_public(self) -> dict[str, str]:
        return {
            "intent_id": self.intent_id,
            "signal_ref": self.signal_ref,
            "strategy_id": self.strategy_id,
            "strategy_version": self.strategy_version,
            "instrument_id": self.instrument_id,
            "status": self.status.value,
            "qualification_artifact_sha256": self.qualification_artifact_sha256,
            "dataset_version": self.dataset_version,
            "selected_config_hash": self.selected_config_hash,
            "quality": self.quality,
        }


@dataclass(frozen=True)
class PortfolioConstructionRequest:
    request_id: str
    portfolio_snapshot: PortfolioSnapshotInput
    intents: tuple[TradingIntentProposal, ...]
    qualifications: tuple[StrategyQualificationEvidence, ...]
    instrument_metadata: tuple[InstrumentMetadata, ...]
    market_history: tuple[tuple[str, tuple[HistoricalBar, ...]], ...]
    market_data_snapshot_ref: str
    market_data_mode: str
    market_data_quality: str
    decision_time: datetime
    construction_policy_version: str
    risk_budget_version: str

    @classmethod
    def create(
        cls,
        *,
        portfolio_snapshot: PortfolioSnapshotInput,
        intents: tuple[TradingIntentProposal, ...] | list[TradingIntentProposal],
        qualifications: tuple[StrategyQualificationEvidence, ...] | list[StrategyQualificationEvidence],
        instrument_metadata: tuple[InstrumentMetadata, ...] | list[InstrumentMetadata],
        market_history: dict[str, tuple[HistoricalBar, ...] | list[HistoricalBar]],
        market_data_snapshot_ref: str,
        market_data_mode: str,
        market_data_quality: str,
        decision_time: datetime,
        construction_policy_version: str,
        risk_budget_version: str,
    ) -> "PortfolioConstructionRequest":
        if decision_time.tzinfo is None or decision_time.tzinfo.utcoffset(decision_time) is None:
            raise ValueError("decision_time must be timezone-aware")
        intents_t = tuple(sorted(intents, key=lambda x: x.intent_id))
        quals_t = tuple(sorted(qualifications, key=lambda x: (x.intent_id, x.strategy_id)))
        metadata_t = tuple(sorted(instrument_metadata, key=lambda x: x.instrument_id))
        intent_ids = [x.intent_id for x in intents_t]
        if len(intent_ids) != len(set(intent_ids)):
            raise ValueError("duplicate intent identity")
        qualification_keys = [(x.intent_id, x.strategy_id) for x in quals_t]
        if len(qualification_keys) != len(set(qualification_keys)):
            raise ValueError("duplicate qualification identity")
        metadata_ids = [x.instrument_id for x in metadata_t]
        if len(metadata_ids) != len(set(metadata_ids)):
            raise ValueError("duplicate instrument metadata identity")
        history_t = tuple(
            (instrument_id, tuple(sorted(rows, key=lambda b: (b.available_at, b.source_record_id))))
            for instrument_id, rows in sorted(market_history.items())
        )
        identity = {
            "portfolio_snapshot": portfolio_snapshot.to_public(),
            "intents": [
                {
                    "intent_id": i.intent_id,
                    "signal_refs": list(i.signal_refs),
                    "instrument_id": i.instrument_id,
                    "direction": i.direction.value,
                    "valid_until": i.valid_until.isoformat(),
                    "quality": i.quality,
                    "generated_at": i.generated_at.isoformat() if i.generated_at else None,
                    "data_mode": i.data_mode,
                    "strategy_id": i.strategy_id,
                    "strategy_version": i.strategy_version,
                }
                for i in intents_t
            ],
            "qualifications": [q.to_public() for q in quals_t],
            "instrument_metadata": [m.to_public() for m in metadata_t],
            "history": [
                {
                    "instrument_id": instrument_id,
                    "rows": [
                        {
                            "source_record_id": b.source_record_id,
                            "revision_id": b.revision_id,
                            "available_at": b.available_at.isoformat(),
                            "close": str(b.close),
                            "quality": b.quality.value,
                        }
                        for b in rows
                    ],
                }
                for instrument_id, rows in history_t
            ],
            "market_data_snapshot_ref": market_data_snapshot_ref,
            "market_data_mode": market_data_mode,
            "market_data_quality": market_data_quality,
            "decision_time": decision_time.isoformat(),
            "construction_policy_version": construction_policy_version,
            "risk_budget_version": risk_budget_version,
        }
        request_id = "pcreq_" + sha256(
            json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:24]
        return cls(
            request_id,
            portfolio_snapshot,
            intents_t,
            quals_t,
            metadata_t,
            history_t,
            market_data_snapshot_ref,
            market_data_mode,
            market_data_quality,
            decision_time,
            construction_policy_version,
            risk_budget_version,
        )

    def history_for(self, instrument_id: str) -> tuple[HistoricalBar, ...]:
        return dict(self.market_history).get(instrument_id, ())


@dataclass(frozen=True)
class ConstraintEffect:
    instrument_id: str
    reason_code: ConstructionReasonCode
    before_weight: Decimal
    after_weight: Decimal
    policy_ref: str
    detail: str = ""

    def to_public(self) -> dict[str, str]:
        return {
            "instrument_id": self.instrument_id,
            "reason_code": self.reason_code.value,
            "before_weight": str(self.before_weight),
            "after_weight": str(self.after_weight),
            "policy_ref": self.policy_ref,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class RejectedIntent:
    intent_id: str
    instrument_id: str
    reason_code: ConstructionReasonCode

    def to_public(self) -> dict[str, str]:
        return {
            "intent_id": self.intent_id,
            "instrument_id": self.instrument_id,
            "reason_code": self.reason_code.value,
        }


@dataclass(frozen=True)
class InstrumentAllocation:
    instrument_id: str
    symbol: str
    asset_class: AssetClass
    quote_currency: str
    current_weight: Decimal
    target_weight: Decimal
    weight_change: Decimal
    target_notional: Decimal
    estimated_cost: Decimal
    strategy_ids: tuple[str, ...] = ()
    intent_ids: tuple[str, ...] = ()
    reason_codes: tuple[ConstructionReasonCode, ...] = ()

    def to_public(self) -> dict[str, Any]:
        return {
            "instrument_id": self.instrument_id,
            "symbol": self.symbol,
            "asset_class": self.asset_class.value,
            "quote_currency": self.quote_currency,
            "current_weight": str(self.current_weight),
            "target_weight": str(self.target_weight),
            "weight_change": str(self.weight_change),
            "target_notional": str(self.target_notional),
            "estimated_cost": str(self.estimated_cost),
            "strategy_ids": list(self.strategy_ids),
            "intent_ids": list(self.intent_ids),
            "reason_codes": [r.value for r in self.reason_codes],
        }


@dataclass(frozen=True)
class CandidatePortfolio:
    candidate_portfolio_id: str
    request_id: str
    fund_id: str
    status: CandidatePortfolioStatus
    portfolio_snapshot_ref: str
    market_data_snapshot_ref: str
    construction_policy_version: str
    risk_budget_version: str
    decision_time: datetime
    allocations: tuple[InstrumentAllocation, ...]
    cash_current_weight: Decimal
    cash_target_weight: Decimal
    turnover: Decimal
    estimated_cost: Decimal
    rejected_intents: tuple[RejectedIntent, ...]
    constraint_effects: tuple[ConstraintEffect, ...]
    reason_codes: tuple[ConstructionReasonCode, ...]
    intent_ids: tuple[str, ...]
    strategy_ids: tuple[str, ...]
    qualification_artifact_sha256: tuple[str, ...]
    dataset_versions: tuple[str, ...]
    selected_config_hashes: tuple[str, ...]
    policy_assumption_status: str
    quality: str
    market_data_mode: str
    authorizes_execution: bool = False
    risk_approved: bool = False
    mode: str = "PAPER"

    def to_public(self) -> dict[str, Any]:
        return {
            "candidate_portfolio_id": self.candidate_portfolio_id,
            "request_id": self.request_id,
            "fund_id": self.fund_id,
            "status": self.status.value,
            "proposal_state": "PROPOSED",
            "portfolio_snapshot_ref": self.portfolio_snapshot_ref,
            "market_data_snapshot_ref": self.market_data_snapshot_ref,
            "construction_policy_version": self.construction_policy_version,
            "risk_budget_version": self.risk_budget_version,
            "decision_time": self.decision_time.isoformat(),
            "allocations": [x.to_public() for x in self.allocations],
            "cash_current_weight": str(self.cash_current_weight),
            "cash_target_weight": str(self.cash_target_weight),
            "turnover": str(self.turnover),
            "estimated_cost": str(self.estimated_cost),
            "rejected_intents": [x.to_public() for x in self.rejected_intents],
            "constraint_effects": [x.to_public() for x in self.constraint_effects],
            "reason_codes": [x.value for x in self.reason_codes],
            "intent_ids": list(self.intent_ids),
            "strategy_ids": list(self.strategy_ids),
            "qualification_artifact_sha256": list(self.qualification_artifact_sha256),
            "dataset_versions": list(self.dataset_versions),
            "selected_config_hashes": list(self.selected_config_hashes),
            "policy_assumption_status": self.policy_assumption_status,
            "quality": self.quality,
            "market_data_mode": self.market_data_mode,
            "authorizes_execution": False,
            "risk_approved": False,
            "mode": "PAPER",
            "live_execution": "UNAVAILABLE",
        }


# Reason codes
RC_SIGNAL_STRENGTH_INCREASE = "SIGNAL_STRENGTH_INCREASE"
RC_TARGET_WEIGHT_RESTORE = "TARGET_WEIGHT_RESTORE"
RC_RISK_CONCENTRATION_REDUCTION = "RISK_CONCENTRATION_REDUCTION"
RC_CASH_BUFFER_RESTORE = "CASH_BUFFER_RESTORE"
RC_POSITION_EXIT = "POSITION_EXIT"
RC_POSITION_ENTRY = "POSITION_ENTRY"
RC_NO_MATERIAL_DRIFT = "NO_MATERIAL_DRIFT"
RC_EQUAL_WEIGHT_BASELINE = "EQUAL_WEIGHT_BASELINE"
RC_FIXED_TARGET = "FIXED_TARGET"
RC_TARGET_REDUCED_MAX_POSITION_LIMIT = "TARGET_REDUCED_MAX_POSITION_LIMIT"
RC_TARGET_REDUCED_CASH_BUFFER = "TARGET_REDUCED_CASH_BUFFER"
RC_TARGET_REDUCED_GROSS_EXPOSURE = "TARGET_REDUCED_GROSS_EXPOSURE"
RC_MIN_TRADE_THRESHOLD = "MIN_TRADE_THRESHOLD"
RC_STALE_PRICE = "STALE_PRICE"
RC_LEDGER_UNRECONCILED = "LEDGER_UNRECONCILED"
RC_INSUFFICIENT_CASH = "INSUFFICIENT_CASH"
RC_WEIGHT_SUM_INVALID = "WEIGHT_SUM_INVALID"
RC_SHORTS_DISABLED = "SHORTS_DISABLED"
RC_LEVERAGE_DISABLED = "LEVERAGE_DISABLED"
RC_UNIVERSE_EXCLUDED = "UNIVERSE_EXCLUDED"
RC_EXPIRED = "EXPIRED"
RC_SUPERSEDED = "SUPERSEDED"
RC_STALE_PROPOSAL = "STALE_PROPOSAL"
RC_RISK_BLOCKED = "RISK_BLOCKED"
RC_NO_ELIGIBLE_UNIVERSE = "NO_ELIGIBLE_UNIVERSE"


def new_proposal_id() -> str:
    return f"pprop_{uuid.uuid4().hex[:16]}"


@dataclass
class MarkQuote:
    security_id: str
    symbol: str
    price: Decimal
    source: str
    timestamp: float
    max_age_seconds: float = 86400.0

    def is_stale(self, now: float | None = None) -> bool:
        now = _time.time() if now is None else now
        return (now - self.timestamp) > self.max_age_seconds

    def to_public(self) -> dict:
        return {
            "security_id": self.security_id,
            "symbol": self.symbol,
            "price": str(q_price(self.price)),
            "source": self.source,
            "timestamp": self.timestamp,
            "freshness": "STALE" if self.is_stale() else "OK",
            "max_age_seconds": self.max_age_seconds,
        }


@dataclass
class UniverseMember:
    security_id: str
    symbol: str
    status: UniverseStatus
    reason_code: str = ""
    signal_strength: Decimal | None = None  # optional 0..1

    def to_public(self) -> dict:
        return {
            "security_id": self.security_id,
            "symbol": self.symbol,
            "status": self.status.value,
            "reason_code": self.reason_code,
            "signal_strength": str(self.signal_strength) if self.signal_strength is not None else None,
        }


@dataclass
class TargetAllocation:
    security_id: str
    symbol: str
    target_weight: Decimal
    target_notional: Decimal = field(default_factory=lambda: Decimal("0"))
    target_quantity: Decimal | None = None
    reason_codes: list[str] = field(default_factory=list)

    def to_public(self) -> dict:
        return {
            "security_id": self.security_id,
            "symbol": self.symbol,
            "target_weight": str(q_money(self.target_weight)),
            "target_notional": str(q_money(self.target_notional)),
            "target_quantity": str(q_qty(self.target_quantity)) if self.target_quantity is not None else None,
            "reason_codes": list(self.reason_codes),
        }


@dataclass
class RebalanceTrade:
    security_id: str
    symbol: str
    action: RebalanceAction
    current_weight: Decimal
    target_weight: Decimal
    weight_delta: Decimal
    current_notional: Decimal
    target_notional: Decimal
    notional_delta: Decimal
    estimated_quantity: Decimal
    reference_price: Decimal
    reason_codes: list[str] = field(default_factory=list)

    def to_public(self) -> dict:
        return {
            "security_id": self.security_id,
            "symbol": self.symbol,
            "action": self.action.value,
            "current_weight": str(q_money(self.current_weight)),
            "target_weight": str(q_money(self.target_weight)),
            "weight_delta": str(q_money(self.weight_delta)),
            "current_notional": str(q_money(self.current_notional)),
            "target_notional": str(q_money(self.target_notional)),
            "notional_delta": str(q_money(self.notional_delta)),
            "estimated_quantity": str(q_qty(self.estimated_quantity)),
            "reference_price": str(q_price(self.reference_price)),
            "reason_codes": list(self.reason_codes),
        }


@dataclass
class PortfolioProposal:
    proposal_id: str
    fund_id: str
    created_at: float
    method: ConstructionMethod
    status: ProposalStatus
    portfolio_snapshot_ref: str
    risk_budget_version: str
    source: str = "portfolio_construction"
    cash_weight: Decimal = field(default_factory=lambda: Decimal("0"))
    target_allocations: list[TargetAllocation] = field(default_factory=list)
    trades: list[RebalanceTrade] = field(default_factory=list)
    projected_cash: Decimal = field(default_factory=lambda: Decimal("0"))
    projected_nav: Decimal = field(default_factory=lambda: Decimal("0"))
    projected_exposure: dict = field(default_factory=dict)
    projected_risk: dict = field(default_factory=dict)
    current_summary: dict = field(default_factory=dict)
    proposed_summary: dict = field(default_factory=dict)
    delta_summary: dict = field(default_factory=dict)
    turnover: Decimal = field(default_factory=lambda: Decimal("0"))
    warnings: list[str] = field(default_factory=list)
    reason_codes: list[str] = field(default_factory=list)
    evidence_refs: dict = field(default_factory=dict)
    market_price_snapshot_ref: str = ""
    valid_until: float | None = None
    supersedes_proposal_id: str = ""
    engine_version: str = "portfolio-construction/1.0.0"
    authorizes_execution: bool = False
    mode: str = "PAPER"

    def to_public(self) -> dict:
        return {
            "proposal_id": self.proposal_id,
            "id": self.proposal_id,
            "fund_id": self.fund_id,
            "created_at": self.created_at,
            "expires_at": self.valid_until,
            "method": self.method.value,
            "status": self.status.value,
            "source": self.source,
            "portfolio_snapshot_ref": self.portfolio_snapshot_ref,
            "risk_budget_version": self.risk_budget_version,
            "market_price_snapshot_ref": self.market_price_snapshot_ref,
            "cash_weight": str(q_money(self.cash_weight)),
            "target_allocations": [t.to_public() for t in self.target_allocations],
            "trades": [t.to_public() for t in self.trades],
            "projected_cash": str(q_money(self.projected_cash)),
            "projected_nav": str(q_money(self.projected_nav)),
            "projected_exposure": self.projected_exposure,
            "projected_risk": self.projected_risk,
            "current": self.current_summary,
            "proposed": self.proposed_summary,
            "delta": self.delta_summary,
            "turnover": str(q_money(self.turnover)),
            "warnings": list(self.warnings),
            "reason_codes": list(self.reason_codes),
            "evidence_refs": dict(self.evidence_refs),
            "supersedes_proposal_id": self.supersedes_proposal_id or None,
            "engine_version": self.engine_version,
            "authorizes_execution": False,
            "mode": "PAPER",
            "live_execution": "UNAVAILABLE",
        }

    def command_contract(self) -> dict:
        """UI-NEXT-3 ready portfolio_proposal shape."""
        pub = self.to_public()
        return {
            "portfolio_proposal": {
                "id": pub["id"],
                "status": pub["status"],
                "created_at": pub["created_at"],
                "expires_at": pub["expires_at"],
                "source": pub["source"],
                "method": pub["method"],
                "current": pub["current"],
                "proposed": pub["proposed"],
                "delta": pub["delta"],
                "trades": pub["trades"],
                "projected_risk": pub["projected_risk"],
                "warnings": pub["warnings"],
                "reason_codes": pub["reason_codes"],
                "evidence_refs": pub["evidence_refs"],
                "approval_status": None,
                "authorizes_execution": False,
                "mode": "PAPER",
            }
        }
