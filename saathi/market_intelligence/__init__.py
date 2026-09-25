"""SaathiOS Market Intelligence Fusion + Catalyst Engine (v1).

Read-only, deterministic, point-in-time-safe layer ABOVE the frozen Research
Surface (b771d761). A catalyst is an observed market/company event WITH context —
never a trade signal. Zero trade authority.
"""
from saathi.market_intelligence.catalyst import (
    CatalystEvent, CatalystPriority, MarketContext, MarketContextStatus, PortfolioContext,
    PortfolioContextStatus, RiskContext, RiskContextStatus, FORBIDDEN_TRADE_TOKENS,
    compute_priority,
)
from saathi.market_intelligence.market_reaction import compute_market_reaction
from saathi.market_intelligence.fusion import (
    MarketIntelligenceSnapshot, build_snapshot, build_from_store, fuse,
    central_command_projection, chat_answer, voice_answer,
)

__all__ = [
    "CatalystEvent", "CatalystPriority", "MarketContext", "MarketContextStatus",
    "PortfolioContext", "PortfolioContextStatus", "RiskContext", "RiskContextStatus",
    "FORBIDDEN_TRADE_TOKENS", "compute_priority", "compute_market_reaction",
    "MarketIntelligenceSnapshot", "build_snapshot", "build_from_store", "fuse",
    "central_command_projection", "chat_answer", "voice_answer",
]
