"""M17 recovery + replanning classifier.

Detects unexpected UI states and decides the safe next move: preserve evidence,
retry safely (only when reversible + prior attempt provably did not succeed +
budget remains), replan, or PAUSE for the user (CAPTCHA/MFA/secure input). Never
repeat-clicks when the UI state is uncertain.
"""
from __future__ import annotations

from enum import Enum


class Obstacle(str, Enum):
    LAYOUT_CHANGE = "layout_change"
    UNEXPECTED_DIALOG = "unexpected_dialog"
    SESSION_EXPIRED = "session_expired"
    LOGIN_SCREEN = "login_screen"
    CAPTCHA = "captcha"
    MFA = "mfa"
    NETWORK_ERROR = "network_error"
    BROWSER_CRASH = "browser_crash"
    APP_CRASH = "app_crash"
    MISSING_ELEMENT = "missing_element"
    STALE_SELECTOR = "stale_selector"
    GEOMETRY_CHANGE = "geometry_change"
    PERMISSION_PROMPT = "permission_prompt"
    SECURE_INPUT = "secure_input"
    FILE_PICKER = "file_picker"
    DOWNLOAD_FAILED = "download_failed"


# obstacles that MUST pause for the user (never automated)
_PAUSE_FOR_USER = {Obstacle.CAPTCHA, Obstacle.MFA, Obstacle.SECURE_INPUT,
                   Obstacle.PERMISSION_PROMPT, Obstacle.LOGIN_SCREEN}
# obstacles that are transient + safe to retry (if action reversible)
_RETRYABLE = {Obstacle.NETWORK_ERROR, Obstacle.MISSING_ELEMENT,
              Obstacle.STALE_SELECTOR, Obstacle.LAYOUT_CHANGE, Obstacle.GEOMETRY_CHANGE}


def plan(*, obstacle: Obstacle, reversible: bool, retry_budget: int,
         prior_attempt_succeeded_unknown: bool) -> dict:
    """Decide the safe recovery move. Ambiguous prior outcome + irreversible ⇒
    never retry (could double-apply)."""
    if obstacle in _PAUSE_FOR_USER:
        return {"decision": "pause_for_user", "obstacle": obstacle.value,
                "capture_disabled": obstacle in (Obstacle.CAPTCHA, Obstacle.MFA,
                                                 Obstacle.SECURE_INPUT)}
    if obstacle in (Obstacle.BROWSER_CRASH, Obstacle.APP_CRASH,
                    Obstacle.SESSION_EXPIRED):
        return {"decision": "replan_from_checkpoint", "obstacle": obstacle.value}
    if obstacle in _RETRYABLE:
        if not reversible and prior_attempt_succeeded_unknown:
            return {"decision": "stop_uncertain", "obstacle": obstacle.value,
                    "reason": "irreversible action with uncertain prior outcome"}
        if retry_budget <= 0:
            return {"decision": "stop_no_progress", "obstacle": obstacle.value}
        return {"decision": "retry_safe", "obstacle": obstacle.value,
                "remaining_budget": retry_budget - 1}
    return {"decision": "request_manual_assistance", "obstacle": obstacle.value}
