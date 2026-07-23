"""M49.2 async/HTTP request classification helpers (no live paid calls)."""
from __future__ import annotations

from enum import Enum


class HttpRequestPhase(str, Enum):
    REQUEST_NEVER_SENT = "REQUEST_NEVER_SENT"
    REQUEST_SEND_FAILED = "REQUEST_SEND_FAILED"
    REQUEST_SENT_NO_RESPONSE = "REQUEST_SENT_NO_RESPONSE"
    RESPONSE_PARTIAL = "RESPONSE_PARTIAL"
    RESPONSE_COMPLETED = "RESPONSE_COMPLETED"
    CANCELLED_BEFORE_SEND = "CANCELLED_BEFORE_SEND"
    TIMEOUT = "TIMEOUT"


def classify_http_outcome(
    *,
    phase: HttpRequestPhase | str,
    side_effect_class: str,
    cancelled: bool = False,
) -> dict:
    """Map request phase to tool outcome honesty rules."""
    phase = HttpRequestPhase(phase) if not isinstance(phase, HttpRequestPhase) else phase
    mutating = side_effect_class not in (
        "",
        "NO_SIDE_EFFECT",
        "LOCAL_REVERSIBLE",
        "FINANCIAL_ADVISORY",
    )
    if cancelled and phase in (
        HttpRequestPhase.REQUEST_NEVER_SENT,
        HttpRequestPhase.CANCELLED_BEFORE_SEND,
    ):
        return {
            "outcome_class": "CANCELLED_CONFIRMED",
            "retryable": False,
            "side_effect_confirmed": True,
        }
    if phase == HttpRequestPhase.RESPONSE_COMPLETED:
        return {
            "outcome_class": "SUCCESS_CONFIRMED",
            "retryable": False,
            "side_effect_confirmed": True,
        }
    if phase in (
        HttpRequestPhase.REQUEST_NEVER_SENT,
        HttpRequestPhase.REQUEST_SEND_FAILED,
        HttpRequestPhase.CANCELLED_BEFORE_SEND,
    ):
        return {
            "outcome_class": "FAILURE_CONFIRMED",
            "retryable": not mutating,
            "side_effect_confirmed": True,
        }
    if phase in (
        HttpRequestPhase.REQUEST_SENT_NO_RESPONSE,
        HttpRequestPhase.RESPONSE_PARTIAL,
        HttpRequestPhase.TIMEOUT,
    ):
        if mutating:
            return {
                "outcome_class": "SIDE_EFFECT_UNKNOWN",
                "retryable": False,
                "side_effect_confirmed": False,
            }
        return {
            "outcome_class": "TIMEOUT_CONFIRMED"
            if phase == HttpRequestPhase.TIMEOUT
            else "FAILURE_CONFIRMED",
            "retryable": True,
            "side_effect_confirmed": True,
        }
    return {
        "outcome_class": "TOOL_OUTCOME_UNKNOWN",
        "retryable": False,
        "side_effect_confirmed": False,
    }
