"""VOICE-1 — voice may observe and ask; it may never execute or approve."""
import pytest

from saathi.platform.tg.voice_trading import (
    RefusalReason, VoiceIntent, boundary, classify,
)


# ── allowed observation (the handover's example intents) ─────────────────────────
@pytest.mark.parametrize("utterance,intent", [
    ("What's my portfolio risk?", VoiceIntent.OBSERVE_RISK),
    ("Why was BTC allocation reduced?", VoiceIntent.OBSERVE_EVIDENCE),
    ("What is Guardian blocking?", VoiceIntent.OBSERVE_GUARDIAN),
    ("Show today's paper performance.", VoiceIntent.OBSERVE_PERFORMANCE),
    ("What evidence supports the BTC strategy?", VoiceIntent.OBSERVE_EVIDENCE),
    ("What's stale?", VoiceIntent.OBSERVE_DATA_QUALITY),
    ("Show me my positions", VoiceIntent.OBSERVE_PORTFOLIO),
])
def test_allowed_observation_intents(utterance, intent):
    d = classify(utterance)
    assert d.allowed is True
    assert d.intent == intent
    assert d.authorizes_execution is False
    assert d.authorizes_approval is False


def test_research_and_proposal_allowed():
    assert classify("research the ETH breakout setup").intent == VoiceIntent.REQUEST_RESEARCH
    assert classify("propose an allocation").intent == VoiceIntent.REQUEST_PROPOSAL
    assert classify("propose an allocation").authorizes_execution is False


# ── hard refusals ────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("utterance,reason", [
    ("buy 1 BTC now", RefusalReason.EXECUTION_BY_VOICE),
    ("sell all my ETH", RefusalReason.EXECUTION_BY_VOICE),
    ("place order for BTCUSDT", RefusalReason.EXECUTION_BY_VOICE),
    ("close position in BTC", RefusalReason.EXECUTION_BY_VOICE),
    ("approve the pending proposal", RefusalReason.APPROVAL_BY_VOICE),
    ("yes do it", RefusalReason.APPROVAL_BY_VOICE),
    ("disable kill switch", RefusalReason.SAFETY_CONTROL_BY_VOICE),
    ("bypass guardian for this trade", RefusalReason.SAFETY_CONTROL_BY_VOICE),
    ("override risk limits", RefusalReason.SAFETY_CONTROL_BY_VOICE),
    ("withdraw my funds", RefusalReason.MONEY_MOVEMENT_BY_VOICE),
    ("transfer funds to my bank", RefusalReason.MONEY_MOVEMENT_BY_VOICE),
])
def test_refused_intents(utterance, reason):
    d = classify(utterance)
    assert d.allowed is False
    assert d.intent == VoiceIntent.REFUSED
    assert d.refusal == reason


def test_refusal_wins_over_observational_half():
    # A mixed utterance must not slip through on its harmless half.
    d = classify("show me the portfolio and approve the order")
    assert d.allowed is False
    assert d.refusal == RefusalReason.APPROVAL_BY_VOICE


def test_execution_not_rescued_by_question_framing():
    d = classify("what is my risk if you buy 1 BTC now")
    assert d.allowed is False
    assert d.refusal == RefusalReason.EXECUTION_BY_VOICE


# ── ambiguity resolves to refusal, never to action ───────────────────────────────
@pytest.mark.parametrize("utterance", ["", "   ", "do the thing", "go ahead", "handle it"])
def test_ambiguous_or_unknown_is_refused(utterance):
    d = classify(utterance)
    assert d.allowed is False
    assert d.intent == VoiceIntent.REFUSED


def test_boundary_declaration():
    b = boundary()
    assert b["may_execute_order"] is False
    assert b["may_approve"] is False
    assert b["may_disable_safety_control"] is False
    assert b["may_move_money"] is False
    assert b["ambiguous_resolves_to"] == "REFUSED"
