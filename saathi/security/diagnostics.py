"""Passkey / Authentication diagnostic messages.

Maps WebAuthn errors, browser exceptions, and OAuth failures to human-readable,
actionable messages. The frontend uses these to show helpful error states
instead of generic "Passkey Failed".
"""
from __future__ import annotations


# ── Passkey / WebAuthn diagnostics ───────────────────────────────────────────

PASSKEY_DIAGNOSTICS = {
    # DOMException names from navigator.credentials.get()
    "NotAllowedError": {
        "user_cancelled": "You cancelled the biometric prompt. Try again when you're ready.",
        "timeout": "The biometric prompt timed out. Try again within 30 seconds.",
        "default": "Biometric authentication was not allowed. Check your browser permissions.",
    },
    "NotSupportedError": {
        "default": "Your browser doesn't support passkeys. Use Chrome, Safari, or Edge.",
        "platform": "Face ID / Touch ID is not available on this device. Set up biometrics in system settings.",
    },
    "SecurityError": {
        "default": "Passkeys require a secure HTTPS connection. Ensure you're on https://...",
        "insecure": "Passkeys cannot work on HTTP. Use HTTPS or localhost.",
    },
    "InvalidStateError": {
        "default": "No passkey found for this device. Register a passkey first.",
        "credential": "The stored passkey is no longer valid. Remove and re-register it.",
    },
    "ConstraintError": {
        "default": "RP ID mismatch. The domain doesn't match the registered passkey.",
    },
    "AbortError": {
        "default": "The operation was aborted. Try again.",
    },
    "TypeError": {
        "default": "Invalid passkey configuration. Contact support.",
    },
    # WebAuthn verification errors (from backend)
    "verification_failed": "Passkey verification failed. The biometric data didn't match.",
    "challenge_mismatch": "Security challenge mismatch. This may indicate a replay attack.",
    "origin_mismatch": "The request origin doesn't match the registered domain.",
    "rp_id_mismatch": "RP ID mismatch. Check your domain configuration.",
    "no_credential": "No passkey credential available for this device.",
    "user_verification_failed": "User verification failed. Use your device PIN or password.",
    "timeout": "The passkey operation timed out. Try again.",
}


def passkey_diagnostic(error_name: str, sub_reason: str = "default") -> str:
    """Get a human-readable diagnostic for a passkey error."""
    entry = PASSKEY_DIAGNOSTICS.get(error_name, PASSKEY_DIAGNOSTICS.get("verification_failed"))
    if isinstance(entry, dict):
        return entry.get(sub_reason, entry.get("default", "Unknown passkey error."))
    return entry


def passkey_diagnostic_from_exception(exc: Exception) -> str:
    """Extract diagnostic from an exception object."""
    name = getattr(exc, "__name__", "") or type(exc).__name__
    msg = str(exc).lower()

    # Map common message patterns to sub-reasons
    if "cancel" in msg or "user cancelled" in msg:
        return passkey_diagnostic("NotAllowedError", "user_cancelled")
    if "timeout" in msg:
        return passkey_diagnostic("NotAllowedError", "timeout")
    if "https" in msg or "secure" in msg:
        return passkey_diagnostic("SecurityError", "default")
    if "credential" in msg and "not found" in msg:
        return passkey_diagnostic("InvalidStateError", "default")
    if "rp id" in msg or "rp_id" in msg:
        return passkey_diagnostic("ConstraintError", "default")
    if "user verification" in msg:
        return passkey_diagnostic("user_verification_failed")

    return passkey_diagnostic(name)


# ── OAuth diagnostics ────────────────────────────────────────────────────────

OAUTH_DIAGNOSTICS = {
    "invalid_client": "OAuth app credentials are invalid. Check your client ID.",
    "invalid_grant": "Authorization code expired or already used. Try signing in again.",
    "unauthorized_client": "This app is not authorized for the requested scope.",
    "access_denied": "You denied access. Grant permission to continue.",
    "unsupported_response_type": "OAuth configuration error. Contact support.",
    "invalid_scope": "The requested permissions are not available.",
    "server_error": "The identity provider is experiencing issues. Try again later.",
    "temporarily_unavailable": "The identity provider is temporarily unavailable. Try again later.",
    "state_mismatch": "Security state mismatch. This may indicate a CSRF attack. Try again.",
    "token_expired": "Your session with the provider expired. Sign in again.",
    "no_email": "The provider did not share your email. Check privacy settings.",
}


def oauth_diagnostic(error_code: str) -> str:
    """Get a human-readable diagnostic for an OAuth error."""
    return OAUTH_DIAGNOSTICS.get(error_code, f"OAuth error: {error_code}. Try again.")
