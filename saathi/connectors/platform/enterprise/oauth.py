"""M15.3 OAuth 2.0 lifecycle state machine (authorization-code + PKCE).

Deterministic, provider-agnostic contract. This implements the SECURITY logic
of the OAuth dance — state validation, PKCE, exact redirect-URI match, user
ownership binding, scope-reduction detection, refresh-no-widen — without a live
provider. Actual token exchange against a real IdP is ENVIRONMENT-BLOCKED here
(no credentials); the exchange/refresh callbacks are injectable so a staging
deployment supplies them. Secrets never persist in these structures.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional


class OAuthState(str, Enum):
    NOT_CONNECTED = "not_connected"
    AUTHORIZATION_PENDING = "authorization_pending"
    CALLBACK_RECEIVED = "callback_received"
    TOKEN_EXCHANGE = "token_exchange"
    CONNECTED = "connected"
    REFRESH_REQUIRED = "refresh_required"
    REFRESHING = "refreshing"
    # terminal / failure
    AUTHORIZATION_DENIED = "authorization_denied"
    INVALID_CALLBACK = "invalid_callback"
    TOKEN_EXCHANGE_FAILED = "token_exchange_failed"
    REFRESH_FAILED = "refresh_failed"
    EXPIRED = "expired"
    REVOKED = "revoked"
    DISCONNECTED = "disconnected"
    BLOCKED = "blocked"


class OAuthError(Exception):
    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code


def _pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    challenge = hashlib.sha256(verifier.encode()).hexdigest()
    return verifier, challenge


@dataclass
class OAuthFlow:
    connector_id: str
    owner: str                         # SaathiOS user the flow is bound to
    redirect_uri: str
    requested_scopes: list = field(default_factory=list)
    state_param: str = ""
    pkce_verifier: str = ""
    pkce_challenge: str = ""
    nonce: str = ""
    created_at: float = 0.0
    ttl_sec: int = 600
    status: str = OAuthState.NOT_CONNECTED.value
    granted_scopes: list = field(default_factory=list)

    def begin(self) -> dict:
        """Start authorization. Returns the params a client needs — never a
        secret. state + PKCE + nonce bind the callback to THIS flow + user."""
        self.state_param = secrets.token_urlsafe(24)
        self.nonce = secrets.token_urlsafe(16)
        self.pkce_verifier, self.pkce_challenge = _pkce_pair()
        self.created_at = time.time()
        self.status = OAuthState.AUTHORIZATION_PENDING.value
        return {"state": self.state_param, "code_challenge": self.pkce_challenge,
                "code_challenge_method": "S256", "nonce": self.nonce,
                "redirect_uri": self.redirect_uri,
                "scope": " ".join(self.requested_scopes)}

    def handle_callback(self, *, state: str, code: str, redirect_uri: str,
                        owner: str, error: str = "",
                        exchange: Optional[Callable[[str, str], dict]] = None) -> dict:
        """Validate + (optionally) exchange. Every mismatch fails CLOSED.

        exchange(code, verifier) -> {access_token, refresh_token?, scope, expires_in}
        is injected by the deployment; absent → token exchange is
        environment-blocked (validation still runs and must pass first).
        """
        if error:
            self.status = OAuthState.AUTHORIZATION_DENIED.value
            raise OAuthError("authorization_denied", error)
        if time.time() - self.created_at > self.ttl_sec:
            self.status = OAuthState.INVALID_CALLBACK.value
            raise OAuthError("invalid_callback", "flow expired")
        # constant-time state comparison (anti-CSRF / anti-substitution)
        if not self.state_param or not hmac.compare_digest(state or "", self.state_param):
            self.status = OAuthState.INVALID_CALLBACK.value
            raise OAuthError("invalid_callback", "state mismatch")
        # exact redirect-URI match
        if redirect_uri != self.redirect_uri:
            self.status = OAuthState.INVALID_CALLBACK.value
            raise OAuthError("invalid_callback", "redirect_uri mismatch")
        # callback must be for the SAME user that began the flow
        if owner != self.owner:
            self.status = OAuthState.INVALID_CALLBACK.value
            raise OAuthError("invalid_callback", "owner mismatch")
        self.status = OAuthState.CALLBACK_RECEIVED.value
        if exchange is None:
            # honest: no live IdP in this environment
            return {"status": OAuthState.TOKEN_EXCHANGE.value,
                    "live_exchange": "environment_blocked"}
        self.status = OAuthState.TOKEN_EXCHANGE.value
        try:
            tok = exchange(code, self.pkce_verifier)
        except Exception as e:
            self.status = OAuthState.TOKEN_EXCHANGE_FAILED.value
            raise OAuthError("token_exchange_failed", str(e))
        granted = (tok.get("scope") or "").split() if isinstance(tok.get("scope"), str) \
            else list(tok.get("scope") or [])
        # scope-reduction detection (informational) + no unexpected expansion
        self._validate_scopes(granted)
        self.granted_scopes = granted
        self.status = OAuthState.CONNECTED.value
        # NOTE: raw tokens are handed to the caller's secret backend, never
        # stored on this dataclass.
        return {"status": self.status, "granted_scopes": granted,
                "scope_reduced": sorted(set(self.requested_scopes) - set(granted)),
                "expires_in": tok.get("expires_in")}

    def _validate_scopes(self, granted: list) -> None:
        expansion = [s for s in granted if s not in self.requested_scopes]
        if expansion:
            self.status = OAuthState.BLOCKED.value
            raise OAuthError("scope_expansion_blocked",
                             f"provider granted unrequested scopes: {expansion}")

    def refresh(self, *, previous_granted: list,
                do_refresh: Optional[Callable[[], dict]] = None) -> dict:
        """Refresh must NOT widen scopes. do_refresh() -> {scope, expires_in}."""
        self.status = OAuthState.REFRESHING.value
        if do_refresh is None:
            self.status = OAuthState.REFRESH_REQUIRED.value
            return {"status": self.status, "live_refresh": "environment_blocked"}
        try:
            tok = do_refresh()
        except Exception as e:
            self.status = OAuthState.REFRESH_FAILED.value
            raise OAuthError("refresh_failed", str(e))
        new_scopes = (tok.get("scope") or "").split() if isinstance(tok.get("scope"), str) \
            else list(tok.get("scope") or previous_granted)
        widened = [s for s in new_scopes if s not in previous_granted]
        if widened:
            self.status = OAuthState.BLOCKED.value
            raise OAuthError("scope_widening_blocked",
                             f"refresh attempted to widen scopes: {widened}")
        self.status = OAuthState.CONNECTED.value
        return {"status": self.status, "granted_scopes": new_scopes,
                "expires_in": tok.get("expires_in")}
