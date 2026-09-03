"""VOICE-1 — voice observation boundary for trading.

Voice may ASK about the portfolio and may request research or a proposal. Voice may
NOT execute a financial order, approve a safety-critical action, disable a control,
or move money — and an ambiguous spoken utterance never resolves toward action.

Classification is deterministic and conservative: anything not clearly an allowed
observation/research intent is REFUSED rather than guessed. Refusal is the default,
not the exception.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class VoiceIntent(str, Enum):
    OBSERVE_PORTFOLIO = "OBSERVE_PORTFOLIO"
    OBSERVE_RISK = "OBSERVE_RISK"
    OBSERVE_GUARDIAN = "OBSERVE_GUARDIAN"
    OBSERVE_PERFORMANCE = "OBSERVE_PERFORMANCE"
    OBSERVE_DATA_QUALITY = "OBSERVE_DATA_QUALITY"
    OBSERVE_EVIDENCE = "OBSERVE_EVIDENCE"
    REQUEST_RESEARCH = "REQUEST_RESEARCH"
    REQUEST_PROPOSAL = "REQUEST_PROPOSAL"
    REFUSED = "REFUSED"


class RefusalReason(str, Enum):
    NONE = "NONE"
    EXECUTION_BY_VOICE = "EXECUTION_BY_VOICE"
    APPROVAL_BY_VOICE = "APPROVAL_BY_VOICE"
    SAFETY_CONTROL_BY_VOICE = "SAFETY_CONTROL_BY_VOICE"
    MONEY_MOVEMENT_BY_VOICE = "MONEY_MOVEMENT_BY_VOICE"
    AMBIGUOUS = "AMBIGUOUS"
    UNRECOGNISED = "UNRECOGNISED"


@dataclass(frozen=True)
class VoiceDecision:
    intent: VoiceIntent
    allowed: bool
    refusal: RefusalReason = RefusalReason.NONE
    detail: str = ""
    # Structural: voice never carries execution or approval authority.
    authorizes_execution: bool = False
    authorizes_approval: bool = False


# Refusal patterns are checked FIRST so "approve and show me" can never slip through
# on the strength of its observational half.
_EXECUTION_TERMS = (
    "buy ", "sell ", "place order", "submit order", "execute", "trade now",
    "close position", "liquidate", "go long", "go short", "market order",
    "limit order", "rebalance now",
)
_APPROVAL_TERMS = ("approve", "authorise", "authorize", "sign off", "confirm the order", "yes do it")
_SAFETY_TERMS = ("disable kill switch", "turn off kill switch", "override risk",
                 "bypass guardian", "raise the limit", "disable the limit", "turn off safety")
_MONEY_TERMS = ("withdraw", "transfer funds", "send money", "deposit", "move money")

# Ordered most-specific first: "portfolio risk" is a risk question, not a generic
# portfolio question, so the broad portfolio pattern is matched last.
_OBSERVE_PATTERNS = (
    (("risk", "drawdown", "limit"), VoiceIntent.OBSERVE_RISK),
    (("guardian", "blocking", "blocked"), VoiceIntent.OBSERVE_GUARDIAN),
    (("stale", "data quality", "feed", "freshness"), VoiceIntent.OBSERVE_DATA_QUALITY),
    (("evidence", "thesis", "why", "support"), VoiceIntent.OBSERVE_EVIDENCE),
    (("performance", "pnl", "p&l", "return", "today"), VoiceIntent.OBSERVE_PERFORMANCE),
    (("portfolio", "position", "holding", "nav", "exposure"), VoiceIntent.OBSERVE_PORTFOLIO),
)
_RESEARCH_TERMS = ("research", "analyse", "analyze", "look into", "investigate")
_PROPOSAL_TERMS = ("propose", "proposal", "what would you suggest", "suggest an allocation")


def classify(utterance: str) -> VoiceDecision:
    """Classify a spoken utterance. Default is refusal."""
    text = str(utterance or "").strip().lower()
    if not text:
        return VoiceDecision(VoiceIntent.REFUSED, False, RefusalReason.UNRECOGNISED, "empty utterance")

    # 1. Hard refusals — checked before anything else.
    for term in _MONEY_TERMS:
        if term in text:
            return VoiceDecision(VoiceIntent.REFUSED, False, RefusalReason.MONEY_MOVEMENT_BY_VOICE,
                                 "money movement is never voice-authorised")
    for term in _SAFETY_TERMS:
        if term in text:
            return VoiceDecision(VoiceIntent.REFUSED, False, RefusalReason.SAFETY_CONTROL_BY_VOICE,
                                 "safety controls are never voice-operated")
    for term in _APPROVAL_TERMS:
        if term in text:
            return VoiceDecision(VoiceIntent.REFUSED, False, RefusalReason.APPROVAL_BY_VOICE,
                                 "approval requires an explicit non-voice action")
    for term in _EXECUTION_TERMS:
        if term in text:
            return VoiceDecision(VoiceIntent.REFUSED, False, RefusalReason.EXECUTION_BY_VOICE,
                                 "voice holds no execution authority")

    # 2. Allowed research / proposal generation (produces proposals, never orders).
    if any(t in text for t in _PROPOSAL_TERMS):
        return VoiceDecision(VoiceIntent.REQUEST_PROPOSAL, True, detail="proposal only; not execution")
    if any(t in text for t in _RESEARCH_TERMS):
        return VoiceDecision(VoiceIntent.REQUEST_RESEARCH, True, detail="research only")

    # 3. Allowed observation.
    for terms, intent in _OBSERVE_PATTERNS:
        if any(t in text for t in terms):
            return VoiceDecision(intent, True, detail="read-only observation")

    # 4. Anything else is refused, never guessed toward action.
    return VoiceDecision(VoiceIntent.REFUSED, False, RefusalReason.UNRECOGNISED,
                         "not a recognised observation intent")


def boundary() -> dict:
    return {
        "may_observe": True,
        "may_request_research": True,
        "may_request_proposal": True,
        "may_execute_order": False,
        "may_approve": False,
        "may_disable_safety_control": False,
        "may_move_money": False,
        "ambiguous_resolves_to": "REFUSED",
    }
