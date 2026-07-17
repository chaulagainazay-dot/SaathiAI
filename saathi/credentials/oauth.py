"""M31 — Provider-neutral OAuth lifecycle with PKCE and replay protection.

Fake providers only. No real token endpoints. Authorization codes never
persisted in durable evidence.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from saathi.credentials.models import OAuthLifecycleState, is_prohibited_provider, is_prohibited_scope


VALID_TRANSITIONS: dict[OAuthLifecycleState, frozenset[OAuthLifecycleState]] = {
    OAuthLifecycleState.UNLINKED: frozenset({
        OAuthLifecycleState.LINK_REQUESTED, OAuthLifecycleState.CANCELLED,
    }),
    OAuthLifecycleState.LINK_REQUESTED: frozenset({
        OAuthLifecycleState.AUTHORIZATION_PENDING, OAuthLifecycleState.CANCELLED, OAuthLifecycleState.FAILED,
    }),
    OAuthLifecycleState.AUTHORIZATION_PENDING: frozenset({
        OAuthLifecycleState.CALLBACK_RECEIVED, OAuthLifecycleState.CANCELLED,
        OAuthLifecycleState.FAILED, OAuthLifecycleState.AUTHORIZATION_PENDING,
    }),
    OAuthLifecycleState.CALLBACK_RECEIVED: frozenset({
        OAuthLifecycleState.TOKEN_EXCHANGE_PENDING, OAuthLifecycleState.FAILED, OAuthLifecycleState.CANCELLED,
    }),
    OAuthLifecycleState.TOKEN_EXCHANGE_PENDING: frozenset({
        OAuthLifecycleState.LINKED, OAuthLifecycleState.FAILED, OAuthLifecycleState.REAUTH_REQUIRED,
    }),
    OAuthLifecycleState.LINKED: frozenset({
        OAuthLifecycleState.REFRESH_REQUIRED, OAuthLifecycleState.REFRESHING,
        OAuthLifecycleState.EXPIRED, OAuthLifecycleState.REVOKING, OAuthLifecycleState.REAUTH_REQUIRED,
    }),
    OAuthLifecycleState.REFRESH_REQUIRED: frozenset({
        OAuthLifecycleState.REFRESHING, OAuthLifecycleState.REAUTH_REQUIRED, OAuthLifecycleState.EXPIRED,
    }),
    OAuthLifecycleState.REFRESHING: frozenset({
        OAuthLifecycleState.LINKED, OAuthLifecycleState.FAILED, OAuthLifecycleState.REAUTH_REQUIRED,
    }),
    OAuthLifecycleState.EXPIRED: frozenset({
        OAuthLifecycleState.REAUTH_REQUIRED, OAuthLifecycleState.REVOKING, OAuthLifecycleState.CANCELLED,
    }),
    OAuthLifecycleState.REAUTH_REQUIRED: frozenset({
        OAuthLifecycleState.AUTHORIZATION_PENDING, OAuthLifecycleState.REVOKING, OAuthLifecycleState.CANCELLED,
    }),
    OAuthLifecycleState.REVOKING: frozenset({
        OAuthLifecycleState.REVOKED, OAuthLifecycleState.FAILED,
    }),
    OAuthLifecycleState.REVOKED: frozenset({OAuthLifecycleState.UNLINKED}),
    OAuthLifecycleState.FAILED: frozenset({
        OAuthLifecycleState.UNLINKED, OAuthLifecycleState.LINK_REQUESTED, OAuthLifecycleState.REAUTH_REQUIRED,
    }),
    OAuthLifecycleState.CANCELLED: frozenset({OAuthLifecycleState.UNLINKED, OAuthLifecycleState.LINK_REQUESTED}),
}


class OAuthError(Exception):
    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code


def generate_state(rng: Optional[Callable[[int], bytes]] = None) -> str:
    if rng is not None:
        return base64.urlsafe_b64encode(rng(24)).decode().rstrip("=")
    return secrets.token_urlsafe(24)


def pkce_pair(rng: Optional[Callable[[int], bytes]] = None) -> tuple[str, str]:
    if rng is not None:
        raw = rng(48)
        verifier = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    else:
        verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).decode().rstrip("=")
    return verifier, challenge


def verify_pkce(verifier: str, challenge: str) -> bool:
    expected = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).decode().rstrip("=")
    return hmac.compare_digest(expected, challenge)


@dataclass
class OAuthSession:
    """In-memory OAuth session — never persists raw codes/tokens to evidence."""

    session_id: str
    provider_id: str
    owner_scope: str
    connector_ids: tuple[str, ...] = ()
    account_link_id: str = ""
    redirect_uri: str = ""
    requested_scopes: tuple[str, ...] = ()
    granted_scopes: tuple[str, ...] = ()
    state: str = OAuthLifecycleState.UNLINKED.value
    state_param: str = ""
    pkce_verifier: str = ""  # held only in process for exchange; not for evidence
    pkce_challenge: str = ""
    created_at: float = 0.0
    expires_at: float = 0.0
    ttl_sec: float = 600.0
    callback_used: bool = False
    approval_token: str = ""
    request_fingerprint: str = ""
    # Transient codes/tokens — process only; never serialize to safe_dict fully
    _auth_code: str = ""
    _access_token: str = ""
    _refresh_token: str = ""
    refresh_attempts: int = 0
    max_refresh_attempts: int = 3

    def to_safe_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "provider_id": self.provider_id,
            "owner_scope": self.owner_scope,
            "connector_ids": list(self.connector_ids),
            "account_link_id": self.account_link_id,
            "redirect_uri": self.redirect_uri,
            "requested_scopes": list(self.requested_scopes),
            "granted_scopes": list(self.granted_scopes),
            "state": self.state,
            "state_param_present": bool(self.state_param),
            "pkce_challenge_present": bool(self.pkce_challenge),
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "callback_used": self.callback_used,
            "refresh_attempts": self.refresh_attempts,
            "contains_secret_values": False,
            # Explicitly omit: state_param value, pkce_verifier, codes, tokens
        }


class OAuthLifecycle:
    """Deterministic OAuth lifecycle manager (fake providers only)."""

    def __init__(
        self,
        *,
        clock: Optional[Callable[[], float]] = None,
        rng: Optional[Callable[[int], bytes]] = None,
        provider: Optional[Any] = None,
    ):
        self.clock = clock or time.time
        self.rng = rng
        self.provider = provider  # FakeOAuthProvider
        self._sessions: dict[str, OAuthSession] = {}
        self._state_index: dict[str, str] = {}  # state_param -> session_id
        self._used_states: set[str] = set()
        self._used_codes: set[str] = set()
        self._lock = threading.RLock()

    def _transition(self, session: OAuthSession, target: OAuthLifecycleState) -> None:
        cur = OAuthLifecycleState(session.state)
        allowed = VALID_TRANSITIONS.get(cur, frozenset())
        if target not in allowed and target is not cur:
            raise OAuthError("illegal_transition", f"{cur.value}->{target.value}")
        session.state = target.value

    def begin_link(
        self,
        *,
        provider_id: str,
        owner_scope: str,
        redirect_uri: str,
        requested_scopes: tuple[str, ...] = (),
        connector_ids: tuple[str, ...] = (),
        account_link_id: str = "",
        approval_token: str = "",
        request_fingerprint: str = "",
        ttl_sec: float = 600.0,
    ) -> dict[str, Any]:
        if is_prohibited_provider(provider_id):
            raise OAuthError("PROHIBITED_PROVIDER")
        for s in requested_scopes:
            if is_prohibited_scope(s):
                raise OAuthError("PROHIBITED_SCOPE", s)
        if not approval_token:
            raise OAuthError("approval_required")
        if not redirect_uri:
            raise OAuthError("redirect_uri_required")

        now = float(self.clock())
        sid = "oauth_" + uuid.uuid4().hex[:14]
        state_param = generate_state(self.rng)
        verifier, challenge = pkce_pair(self.rng)
        session = OAuthSession(
            session_id=sid,
            provider_id=provider_id,
            owner_scope=owner_scope,
            connector_ids=tuple(connector_ids),
            account_link_id=account_link_id,
            redirect_uri=redirect_uri,
            requested_scopes=tuple(requested_scopes),
            state=OAuthLifecycleState.LINK_REQUESTED.value,
            state_param=state_param,
            pkce_verifier=verifier,
            pkce_challenge=challenge,
            created_at=now,
            expires_at=now + ttl_sec,
            ttl_sec=ttl_sec,
            approval_token=approval_token,
            request_fingerprint=request_fingerprint,
        )
        self._transition(session, OAuthLifecycleState.AUTHORIZATION_PENDING)
        with self._lock:
            self._sessions[sid] = session
            self._state_index[state_param] = sid
        return {
            "session_id": sid,
            "state": session.state,
            "authorization": {
                "state": state_param,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "redirect_uri": redirect_uri,
                "scope": " ".join(requested_scopes),
                "provider_id": provider_id,
            },
            "contains_secret_values": False,
        }

    def handle_callback(
        self,
        *,
        state: str,
        code: str = "",
        redirect_uri: str = "",
        provider_id: str = "",
        owner_scope: str = "",
        error: str = "",
        code_verifier: str = "",
    ) -> dict[str, Any]:
        if not state:
            raise OAuthError("missing_state")
        with self._lock:
            if state in self._used_states:
                raise OAuthError("state_reused")
            sid = self._state_index.get(state)
            if sid is None:
                raise OAuthError("mismatched_state")
            session = self._sessions[sid]

        now = float(self.clock())
        if now > session.expires_at:
            self._transition(session, OAuthLifecycleState.FAILED)
            raise OAuthError("expired_state")

        if not hmac.compare_digest(state, session.state_param):
            self._transition(session, OAuthLifecycleState.FAILED)
            raise OAuthError("mismatched_state")

        if redirect_uri != session.redirect_uri:
            self._transition(session, OAuthLifecycleState.FAILED)
            raise OAuthError("incorrect_redirect_uri")

        if provider_id and provider_id != session.provider_id:
            self._transition(session, OAuthLifecycleState.FAILED)
            raise OAuthError("wrong_provider")

        if owner_scope and owner_scope != session.owner_scope:
            self._transition(session, OAuthLifecycleState.FAILED)
            raise OAuthError("wrong_owner")

        if error:
            self._transition(session, OAuthLifecycleState.CANCELLED)
            return {"status": session.state, "reason": error, "contains_secret_values": False}

        if session.callback_used:
            raise OAuthError("callback_replay")

        if not code:
            self._transition(session, OAuthLifecycleState.FAILED)
            raise OAuthError("missing_code")

        # PKCE
        verifier = code_verifier or session.pkce_verifier
        if not verifier:
            raise OAuthError("missing_verifier")
        if not verify_pkce(verifier, session.pkce_challenge):
            self._transition(session, OAuthLifecycleState.FAILED)
            raise OAuthError("incorrect_verifier")

        if code in self._used_codes:
            raise OAuthError("callback_replay")

        self._transition(session, OAuthLifecycleState.CALLBACK_RECEIVED)
        session.callback_used = True
        session._auth_code = code
        with self._lock:
            self._used_states.add(state)
            self._used_codes.add(code)

        # Token exchange via fake provider
        self._transition(session, OAuthLifecycleState.TOKEN_EXCHANGE_PENDING)
        if self.provider is None:
            self._transition(session, OAuthLifecycleState.FAILED)
            raise OAuthError("provider_unavailable")

        try:
            tokens = self.provider.exchange_code(
                code=code,
                code_verifier=verifier,
                redirect_uri=redirect_uri,
                provider_id=session.provider_id,
            )
        except Exception as e:
            self._transition(session, OAuthLifecycleState.FAILED)
            raise OAuthError("token_exchange_failed", type(e).__name__) from e

        granted = tokens.get("scopes") or tokens.get("scope") or list(session.requested_scopes)
        if isinstance(granted, str):
            granted = granted.split()
        granted = list(granted)
        # No silent expansion
        expansion = [s for s in granted if s not in session.requested_scopes]
        if expansion:
            self._transition(session, OAuthLifecycleState.FAILED)
            raise OAuthError("scope_expansion_blocked")

        session.granted_scopes = tuple(granted)
        session._access_token = str(tokens.get("access_token") or "")
        session._refresh_token = str(tokens.get("refresh_token") or "")
        # Clear auth code from process ASAP
        session._auth_code = ""
        self._transition(session, OAuthLifecycleState.LINKED)
        return {
            "status": session.state,
            "session_id": session.session_id,
            "granted_scopes": list(session.granted_scopes),
            "account_link_id": session.account_link_id,
            "has_access_token": bool(session._access_token),
            "has_refresh_token": bool(session._refresh_token),
            "contains_secret_values": False,
        }

    def take_tokens_for_broker(self, session_id: str) -> dict[str, str]:
        """Hand tokens to broker storage once; clear from session."""
        session = self._sessions.get(session_id)
        if session is None or session.state != OAuthLifecycleState.LINKED.value:
            raise OAuthError("not_linked")
        out = {}
        if session._access_token:
            out["access_token"] = session._access_token
        if session._refresh_token:
            out["refresh_token"] = session._refresh_token
        session._access_token = ""
        session._refresh_token = ""
        session.pkce_verifier = ""  # dispose verifier
        return out

    def refresh(self, session_id: str) -> dict[str, Any]:
        session = self._sessions.get(session_id)
        if session is None:
            raise OAuthError("unknown_session")
        if session.refresh_attempts >= session.max_refresh_attempts:
            self._transition(session, OAuthLifecycleState.REAUTH_REQUIRED)
            raise OAuthError("refresh_exhausted")
        self._transition(session, OAuthLifecycleState.REFRESHING)
        session.refresh_attempts += 1
        if self.provider is None:
            self._transition(session, OAuthLifecycleState.REFRESH_REQUIRED)
            raise OAuthError("provider_unavailable")
        try:
            tokens = self.provider.refresh(session_id=session_id)
        except Exception as e:
            self._transition(session, OAuthLifecycleState.REAUTH_REQUIRED)
            raise OAuthError("refresh_failed", type(e).__name__) from e
        new_scopes = tokens.get("scopes") or list(session.granted_scopes)
        if isinstance(new_scopes, str):
            new_scopes = new_scopes.split()
        widened = [s for s in new_scopes if s not in session.granted_scopes and s not in session.requested_scopes]
        if widened:
            self._transition(session, OAuthLifecycleState.FAILED)
            raise OAuthError("scope_widening_blocked")
        session._access_token = str(tokens.get("access_token") or "")
        if tokens.get("refresh_token"):
            session._refresh_token = str(tokens["refresh_token"])
        self._transition(session, OAuthLifecycleState.LINKED)
        return {
            "status": session.state,
            "granted_scopes": list(session.granted_scopes),
            "contains_secret_values": False,
        }

    def cancel(self, session_id: str) -> dict[str, Any]:
        session = self._sessions.get(session_id)
        if session is None:
            raise OAuthError("unknown_session")
        self._transition(session, OAuthLifecycleState.CANCELLED)
        session._access_token = ""
        session._refresh_token = ""
        session._auth_code = ""
        session.pkce_verifier = ""
        return session.to_safe_dict()

    def revoke(self, session_id: str) -> dict[str, Any]:
        session = self._sessions.get(session_id)
        if session is None:
            raise OAuthError("unknown_session")
        if session.state not in (
            OAuthLifecycleState.REVOKING.value,
            OAuthLifecycleState.LINKED.value,
            OAuthLifecycleState.EXPIRED.value,
            OAuthLifecycleState.REAUTH_REQUIRED.value,
            OAuthLifecycleState.REFRESH_REQUIRED.value,
        ):
            # force via REVOKING when possible
            try:
                self._transition(session, OAuthLifecycleState.REVOKING)
            except OAuthError:
                session.state = OAuthLifecycleState.REVOKING.value
        self._transition(session, OAuthLifecycleState.REVOKED)
        session._access_token = ""
        session._refresh_token = ""
        return session.to_safe_dict()

    def get_session(self, session_id: str) -> Optional[OAuthSession]:
        return self._sessions.get(session_id)

    def inspect(self, session_id: str) -> dict[str, Any]:
        s = self._sessions.get(session_id)
        if s is None:
            raise OAuthError("unknown_session")
        return s.to_safe_dict()
