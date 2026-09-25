"""M — MARKET_INTELLIGENCE_FUSION_AND_CATALYST_ENGINE — domain model.

A CatalystEvent is AN OBSERVED MARKET/COMPANY EVENT WITH CONTEXT — never a trade
signal, recommendation, price target, expected return, or position instruction.
This module is deterministic, read-only, LLM-free, and has ZERO trade authority:
it imports no ExecutionGateway, Trading Guardian trade path, broker, portfolio
writer, or market_data writer. It CONSUMES the frozen ResearchEvent taxonomy
(no duplicate taxonomy) and reports typed degraded states rather than fabricating.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

# Reuse the FROZEN research taxonomy — do not duplicate it.
from saathi.browser_research.intelligence import (
    ContradictionState, ResearchEvent, ResearchEventType,
)
from saathi.browser_research.freshness import Freshness
from saathi.browser_research.tiers import SourceTier

SCHEMA = "market_intelligence.catalyst.v1"


class CatalystPriority(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class MarketContextStatus(str, Enum):
    OK = "OK"
    MARKET_DATA_UNAVAILABLE = "MARKET_DATA_UNAVAILABLE"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
    SYMBOL_UNRESOLVED = "SYMBOL_UNRESOLVED"
    TIMESTAMP_UNRESOLVED = "TIMESTAMP_UNRESOLVED"


class PortfolioContextStatus(str, Enum):
    OK = "OK"
    PORTFOLIO_CONTEXT_UNAVAILABLE = "PORTFOLIO_CONTEXT_UNAVAILABLE"
    NOT_HELD = "NOT_HELD"


class RiskContextStatus(str, Enum):
    OK = "OK"
    RISK_CONTEXT_UNAVAILABLE = "RISK_CONTEXT_UNAVAILABLE"


@dataclass(frozen=True)
class MarketContext:
    """Descriptive historical MARKET_REACTION — never expected return / forecast."""
    status: MarketContextStatus
    price_before: str = ""             # strings to avoid implying computed float authority
    price_after: str = ""
    absolute_change: str = ""
    percentage_change: str = ""
    volume_before: str = ""
    volume_after: str = ""
    volume_ratio: str = ""
    window: str = ""                   # e.g. "1_session" | "prev_close->first_close_after_pub"
    sessions_used: int = 0
    detail: str = ""

    def as_dict(self) -> dict:
        return {"status": self.status.value, "window": self.window,
                "price_before": self.price_before, "price_after": self.price_after,
                "absolute_change": self.absolute_change, "percentage_change": self.percentage_change,
                "volume_before": self.volume_before, "volume_after": self.volume_after,
                "volume_ratio": self.volume_ratio, "sessions_used": self.sessions_used,
                "detail": self.detail}


@dataclass(frozen=True)
class PortfolioContext:
    status: PortfolioContextStatus
    portfolio_relevant: bool = False
    watchlist_relevant: bool = False
    holding_quantity: str = ""
    portfolio_weight: str = ""
    exposure_value: str = ""

    def as_dict(self) -> dict:
        return {"status": self.status.value, "portfolio_relevant": self.portfolio_relevant,
                "watchlist_relevant": self.watchlist_relevant,
                "holding_quantity": self.holding_quantity, "portfolio_weight": self.portfolio_weight,
                "exposure_value": self.exposure_value}


@dataclass(frozen=True)
class RiskContext:
    status: RiskContextStatus
    single_name_exposure: str = ""
    concentration_note: str = ""
    event_proximity: str = ""

    def as_dict(self) -> dict:
        return {"status": self.status.value, "single_name_exposure": self.single_name_exposure,
                "concentration_note": self.concentration_note, "event_proximity": self.event_proximity}


@dataclass
class CatalystEvent:
    catalyst_id: str
    research_event_id: str
    event_type: ResearchEventType
    symbol: str
    headline: str
    event_date_raw: str
    publication_ts: float | None
    source_tier: SourceTier
    freshness: Freshness
    confidence: float
    contradiction_state: ContradictionState
    evidence_refs: list = field(default_factory=list)
    document_refs: list = field(default_factory=list)
    market_context: MarketContext = field(default_factory=lambda: MarketContext(MarketContextStatus.MARKET_DATA_UNAVAILABLE))
    portfolio_context: PortfolioContext = field(default_factory=lambda: PortfolioContext(PortfolioContextStatus.PORTFOLIO_CONTEXT_UNAVAILABLE))
    risk_context: RiskContext = field(default_factory=lambda: RiskContext(RiskContextStatus.RISK_CONTEXT_UNAVAILABLE))
    catalyst_priority: CatalystPriority = CatalystPriority.LOW
    priority_reasons: list = field(default_factory=list)
    limitations: list = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "schema": SCHEMA, "catalyst_id": self.catalyst_id,
            "research_event_id": self.research_event_id, "event_type": self.event_type.value,
            "symbol": self.symbol, "headline": self.headline, "event_date_raw": self.event_date_raw,
            "publication_ts": self.publication_ts, "source_tier": self.source_tier.name,
            "freshness": self.freshness.value, "confidence": round(self.confidence, 3),
            "contradiction_state": self.contradiction_state.value,
            "evidence_refs": list(self.evidence_refs), "document_refs": list(self.document_refs),
            "market_context": self.market_context.as_dict(),
            "portfolio_context": self.portfolio_context.as_dict(),
            "risk_context": self.risk_context.as_dict(),
            "catalyst_priority": self.catalyst_priority.value,
            "priority_reasons": list(self.priority_reasons), "limitations": list(self.limitations),
        }


# Event categories that carry higher operator-attention / risk relevance.
_HIGH_ATTENTION = {
    ResearchEventType.DIVIDEND, ResearchEventType.RIGHTS_ISSUE, ResearchEventType.BONUS_SHARE,
    ResearchEventType.DELISTING, ResearchEventType.SUSPENSION, ResearchEventType.RESULT,
    ResearchEventType.MONETARY_POLICY, ResearchEventType.REGULATORY,
    ResearchEventType.SECURITY_INCIDENT,
}

# Forbidden trade-authority tokens — priority/reasons must never emit these as
# recommendations. Asserted by tests.
FORBIDDEN_TRADE_TOKENS = (
    "buy", "sell", "long", "short", "execute", "target price", "position size",
    "price target", "order", "entry", "exit", "take profit", "stop loss",
)


def compute_priority(cat: CatalystEvent) -> tuple[CatalystPriority, list[str]]:
    """Deterministic OPERATOR-ATTENTION / PORTFOLIO-RISK relevance — NOT investment
    attractiveness. Returns (priority, reasons). No trade semantics."""
    reasons: list[str] = []
    score = 0
    if cat.source_tier == SourceTier.TIER_1_OFFICIAL:
        score += 2; reasons.append("TIER_1_OFFICIAL source")
    elif cat.source_tier == SourceTier.TIER_2_PRIMARY_DATA:
        score += 1; reasons.append("primary-data source")
    if cat.freshness in (Freshness.REALTIME, Freshness.NEAR_REALTIME, Freshness.TODAY):
        score += 2; reasons.append(f"fresh event ({cat.freshness.value})")
    elif cat.freshness == Freshness.RECENT:
        score += 1; reasons.append("recent event")
    if cat.event_type in _HIGH_ATTENTION:
        score += 2; reasons.append(f"high-attention category ({cat.event_type.value})")
    if cat.document_refs:
        score += 1; reasons.append("official document attached")
    if cat.contradiction_state == ContradictionState.UNCONFIRMED_MULTI_SOURCE:
        score += 1; reasons.append("unconfirmed multi-source — needs review")
    if cat.portfolio_context.portfolio_relevant:
        score += 2; reasons.append("affects a portfolio holding")
    if cat.market_context.status == MarketContextStatus.OK and cat.market_context.percentage_change:
        try:
            if abs(float(cat.market_context.percentage_change.rstrip("%"))) >= 5.0:
                score += 1; reasons.append("abnormal market reaction (>=5%)")
        except ValueError:
            pass
    if score >= 6:
        return CatalystPriority.HIGH, reasons
    if score >= 3:
        return CatalystPriority.MEDIUM, reasons
    return CatalystPriority.LOW, (reasons or ["low attention: weak source/stale/low-impact"])
