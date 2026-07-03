"""Failure Analyzer — deterministic failure classification (M2 Phase 3, Stage 3).

Don't just record failures — classify them. These categories become invaluable
in Mission Control ("42% of failures were EXTERNAL_API this week"). Rule-based,
never an LLM (AP-17): predictable and auditable.
"""
from __future__ import annotations

import re
from enum import Enum

from saathi.memory.platform import Episode


class FailureCategory(str, Enum):
    INFRASTRUCTURE = "infrastructure"   # disk / memory / GPU / capacity
    REASONING = "reasoning"             # bad plan / logic
    TOOL = "tool"                       # tool errored / unknown tool
    MODEL = "model"                     # LLM output bad / refused
    PROMPT = "prompt"                   # prompt-quality issue
    USER = "user"                       # user input problem
    EXTERNAL_API = "external_api"       # third-party API error / rate limit
    NETWORK = "network"                 # timeout / connection
    HUMAN_APPROVAL = "human_approval"   # blocked pending approval / governance
    UNKNOWN = "unknown"


# Ordered most-specific first; first matching category wins.
_RULES: list[tuple[FailureCategory, re.Pattern]] = [
    (FailureCategory.NETWORK, re.compile(r"\b(timeout|timed out|connection|unreachable|dns|banner)\b")),
    (FailureCategory.EXTERNAL_API, re.compile(r"\b(429|rate.?limit|api error|quota|http 5\d\d|upstream)\b")),
    (FailureCategory.INFRASTRUCTURE, re.compile(r"\b(disk|out of memory|oom|gpu|capacity|out of capacity|storage full|no space)\b")),
    (FailureCategory.HUMAN_APPROVAL, re.compile(r"\b(governance_denied|approval|not permitted|requires human|speaker_not_verified)\b")),
    (FailureCategory.TOOL, re.compile(r"\b(unknown tool|tool error|handler|traceback)\b")),
    (FailureCategory.MODEL, re.compile(r"\b(refused|hallucinat|invalid json|no provider|all providers failed|model)\b")),
    (FailureCategory.PROMPT, re.compile(r"\b(prompt|instruction|malformed request)\b")),
    (FailureCategory.USER, re.compile(r"\b(invalid input|user error|missing field|bad request)\b")),
    (FailureCategory.REASONING, re.compile(r"\b(wrong plan|logic|contradiction|incorrect approach)\b")),
]


def classify_failure(episode: Episode) -> FailureCategory:
    """Deterministic. Scans result + metadata error text for category markers."""
    text = f"{episode.result} {episode.intent}".lower()
    meta = episode.metadata or {}
    for key in ("error", "message", "reason", "failure"):
        if key in meta:
            text += " " + str(meta[key]).lower()
    for category, pat in _RULES:
        if pat.search(text):
            return category
    return FailureCategory.UNKNOWN
