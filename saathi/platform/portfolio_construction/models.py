"""Proposal domain models and reason codes."""
from __future__ import annotations

import time as _time
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any

from saathi.platform.fund_ledger.money import D, q_money, q_price, q_qty


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
