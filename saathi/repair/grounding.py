"""Anti-hallucination grounding — behaviour probes for task-execution failures.

For commands like "Analyze my email" the loop must not trust the final text. It
classifies the *expected* behaviour and then checks the execution trace for
evidence that the right thing happened (a connector was actually called, or
correctly was NOT called). No execution evidence => the task was not executed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class ExpectedBehavior(str, Enum):
    CONVERSATIONAL = "conversational"          # explain/define — no connector
    ANALYZE_PROVIDED = "analyze_provided"      # analyze pasted text — no retrieval
    CONNECTOR_READ = "connector_read"          # fetch real data via gateway
    SIDE_EFFECT_APPROVAL = "side_effect_approval"  # send/write — approval required


@dataclass
class GroundingVerdict:
    expected: ExpectedBehavior
    grounded: bool
    reason: str


def expected_behavior(command: str, *, has_pasted_content: bool = False) -> ExpectedBehavior:
    c = (command or "").lower().strip()
    # side effects first (highest risk)
    if re.search(r"\b(send|reply|forward|email to|message to|delete|post|publish|pay|transfer|buy)\b", c):
        return ExpectedBehavior.SIDE_EFFECT_APPROVAL
    # pasted content -> analyze the text, do NOT hit a connector
    if has_pasted_content or re.search(r"analyze this|here is|:\s*\S+.*\n|following (email|text)", c):
        return ExpectedBehavior.ANALYZE_PROVIDED
    # explain/define -> conversational, no connector
    if re.search(r"^(what is|explain|define|how does|tell me about)\b", c):
        return ExpectedBehavior.CONVERSATIONAL
    # my/latest/show + a connector noun -> real connector read
    if re.search(r"\b(my|latest|show|check|read|get|fetch)\b", c) and \
       re.search(r"\b(email|gmail|inbox|calendar|drive|message|repo)\b", c):
        return ExpectedBehavior.CONNECTOR_READ
    return ExpectedBehavior.CONVERSATIONAL


def verify_grounding(command: str, trace: list[str], *,
                     has_pasted_content: bool = False,
                     connector_authed: bool = True) -> GroundingVerdict:
    """Check the execution trace against the expected behaviour.

    `trace` is the list of execution steps (e.g. ["intent:connector_read",
    "gateway:executed", "connector:gmail:ok"]). Emptiness is meaningful.
    """
    exp = expected_behavior(command, has_pasted_content=has_pasted_content)
    joined = " ".join(trace).lower()
    used_connector = bool(re.search(r"connector[:\s]|gateway:executed", joined))

    if exp == ExpectedBehavior.CONNECTOR_READ:
        if not connector_authed:
            return GroundingVerdict(exp, False,
                "connector not connected or authenticated — the task was not executed")
        if not used_connector:
            return GroundingVerdict(exp, False,
                "connector read expected but no gateway/connector call in trace — "
                "the task was not executed (possible EXECUTION_BYPASS / not grounded)")
        return GroundingVerdict(exp, True, "connector call present in trace")

    if exp == ExpectedBehavior.SIDE_EFFECT_APPROVAL:
        approved = "approval" in joined or "awaiting_approval" in joined
        if used_connector and not approved:
            return GroundingVerdict(exp, False,
                "side effect executed without approval — must require approval")
        return GroundingVerdict(exp, True, "side effect gated by approval")

    # conversational / analyze-provided: a connector call would be WRONG
    if exp in (ExpectedBehavior.CONVERSATIONAL, ExpectedBehavior.ANALYZE_PROVIDED):
        if used_connector:
            return GroundingVerdict(exp, False,
                "no connector expected but trace shows a connector call")
        return GroundingVerdict(exp, True, "no connector used, as expected")

    return GroundingVerdict(exp, True, "ok")
