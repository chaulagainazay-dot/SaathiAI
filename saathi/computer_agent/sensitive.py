"""M17 sensitive-input protection.

Detect sensitive fields (accessibility role, DOM type, visual signals), never
read existing secret values, never capture typed secrets in screenshots/logs/
replay/memory/events, never request MFA/CAPTCHA bypass. When a sensitive field is
the target, the agent PAUSES and asks the user to enter the value personally.
"""
from __future__ import annotations

import re

# accessibility roles / DOM types / label keywords that mark a sensitive field
_SENSITIVE_ROLES = {"AXSecureTextField", "secure_text", "password"}
_SENSITIVE_DOM_TYPES = {"password"}
_SENSITIVE_LABELS = re.compile(
    r"(?i)\b(password|passcode|one[\s-]?time|otp|mfa|2fa|verification code|"
    r"recovery key|private key|api[\s-]?key|token|card number|cvv|cvc|iban|"
    r"account number|ssn|social security|passport)\b")

# screenshot regions to redact + replay marker
REPLAY_MARKER = "Sensitive input entered by user"


def is_sensitive_element(*, role: str = "", dom_type: str = "", label: str = "",
                         text: str = "") -> bool:
    if role in _SENSITIVE_ROLES:
        return True
    if dom_type.lower() in _SENSITIVE_DOM_TYPES:
        return True
    if label and _SENSITIVE_LABELS.search(label):
        return True
    if text and _SENSITIVE_LABELS.search(text):
        return True
    return False


def is_captcha_or_mfa(*, label: str = "", text: str = "", role: str = "") -> str | None:
    hay = f"{label} {text}".lower()
    if any(k in hay for k in ("captcha", "recaptcha", "hcaptcha", "i'm not a robot",
                              "are you human")):
        return "captcha"
    if any(k in hay for k in ("verification code", "one-time", "otp", "2fa",
                              "authenticator", "mfa")):
        return "mfa"
    if "biometr" in hay or "touch id" in hay or "face id" in hay:
        return "biometric"
    return None


def sensitive_pause_plan(kind: str = "sensitive_field") -> dict:
    """What the agent does instead of typing a secret / solving a challenge."""
    return {
        "action": "pause_for_user",
        "reason": kind,
        "capture_disabled": True,           # no screenshot/keystroke capture
        "message": {
            "sensitive_field": "Please enter the sensitive value yourself; I will not read or record it.",
            "captcha": "Please complete the CAPTCHA; I do not bypass anti-bot checks.",
            "mfa": "Please complete MFA on your device; I do not capture codes.",
            "biometric": "Please complete the biometric prompt yourself.",
        }.get(kind, "Please complete this step manually."),
        "resume": "after_user_confirms",
        "replay_marker": REPLAY_MARKER,
    }


def refuse_bypass(kind: str) -> dict:
    """MFA/CAPTCHA/biometric bypass is always refused."""
    return {"allowed": False, "reason": f"{kind}_bypass_refused",
            "message": "Bypassing this security check is not permitted."}
