"""M49.2 async/HTTP request classification helpers (no live paid calls)."""
from __future__ import annotations

from enum import Enum


class HttpRequestPhase(str, Enum):
    """M49.3 request-phase vocabulary (includes M49.2 aliases)."""

    NOT_STARTED = "NOT_STARTED"
    DNS_OR_CONNECT = "DNS_OR_CONNECT"
    CONNECTED = "CONNECTED"
    HEADERS_SENT = "HEADERS_SENT"
    BODY_PARTIAL = "BODY_PARTIAL"
    BODY_SENT = "BODY_SENT"
    RESPONSE_HEADERS = "RESPONSE_HEADERS"
    RESPONSE_PARTIAL = "RESPONSE_PARTIAL"
    RESPONSE_COMPLETE = "RESPONSE_COMPLETE"
    RESPONSE_COMPLETED = "RESPONSE_COMPLETED"  # alias
    UNKNOWN = "UNKNOWN"
    # M49.2 aliases
    REQUEST_NEVER_SENT = "REQUEST_NEVER_SENT"
    REQUEST_SEND_FAILED = "REQUEST_SEND_FAILED"
    REQUEST_SENT_NO_RESPONSE = "REQUEST_SENT_NO_RESPONSE"
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
        HttpRequestPhase.NOT_STARTED,
    ):
        return {
            "outcome_class": "CANCELLED_CONFIRMED",
            "retryable": False,
            "side_effect_confirmed": True,
        }
    if cancelled and phase in (
        HttpRequestPhase.BODY_SENT,
        HttpRequestPhase.HEADERS_SENT,
        HttpRequestPhase.REQUEST_SENT_NO_RESPONSE,
        HttpRequestPhase.RESPONSE_PARTIAL,
        HttpRequestPhase.UNKNOWN,
    ):
        return {
            "outcome_class": "CANCELLATION_UNCONFIRMED"
            if not mutating
            else "SIDE_EFFECT_UNKNOWN",
            "retryable": False,
            "side_effect_confirmed": False,
        }
    if phase in (
        HttpRequestPhase.RESPONSE_COMPLETED,
        HttpRequestPhase.RESPONSE_COMPLETE,
    ):
        return {
            "outcome_class": "SUCCESS_CONFIRMED",
            "retryable": False,
            "side_effect_confirmed": True,
        }
    if phase in (
        HttpRequestPhase.REQUEST_NEVER_SENT,
        HttpRequestPhase.REQUEST_SEND_FAILED,
        HttpRequestPhase.CANCELLED_BEFORE_SEND,
        HttpRequestPhase.NOT_STARTED,
        HttpRequestPhase.DNS_OR_CONNECT,
    ):
        return {
            "outcome_class": "FAILURE_CONFIRMED",
            "retryable": not mutating,
            "side_effect_confirmed": True,
        }
    if phase in (
        HttpRequestPhase.REQUEST_SENT_NO_RESPONSE,
        HttpRequestPhase.RESPONSE_PARTIAL,
        HttpRequestPhase.BODY_SENT,
        HttpRequestPhase.BODY_PARTIAL,
        HttpRequestPhase.HEADERS_SENT,
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
