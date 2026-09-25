"""Financial Browser session model + manager. Provider-scoped, owner-authenticated.

No raw browser cookies/secrets are ever exposed through these contracts. Sessions are
in-memory, on-demand, and isolated per provider. Includes expiry → OWNER_REAUTHENTICATION
and a kill switch that revokes agent capability + clears ephemeral buffers.
"""
from __future__ import annotations

import enum
import time
import uuid
from dataclasses import dataclass, field

from saathi.platform.finance import audit
from saathi.platform.finance.policy import (
    POLICIES, Actor, InteractionMode, Provider, enforce,
)


class SessionAuthState(str, enum.Enum):
    UNAUTHENTICATED = "UNAUTHENTICATED"
    OWNER_AUTHENTICATED = "OWNER_AUTHENTICATED"
    OWNER_AUTH_REQUIRED = "OWNER_AUTH_REQUIRED"
    OWNER_REAUTH_REQUIRED = "OWNER_REAUTH_REQUIRED"
    SESSION_EXPIRED = "SESSION_EXPIRED"


class SecurityState(str, enum.Enum):
    CONNECTED_READ_ONLY = "CONNECTED_READ_ONLY"
    OWNER_AUTH_REQUIRED = "OWNER_AUTH_REQUIRED"
    OWNER_REAUTH_REQUIRED = "OWNER_REAUTH_REQUIRED"
    SESSION_EXPIRED = "SESSION_EXPIRED"
    READ_BLOCKED = "READ_BLOCKED"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    CAPTCHA_REQUIRED = "CAPTCHA_REQUIRED"
    TWO_FACTOR_REQUIRED = "TWO_FACTOR_REQUIRED"
    AGENT_ACTION_BLOCKED = "AGENT_ACTION_BLOCKED"
    KILLED = "KILLED"


DEFAULT_TTL_SEC = 900.0


@dataclass
class FinancialBrowserSession:
    session_id: str
    provider: Provider
    owner_id: str
    created_at: float
    last_active_at: float
    auth_state: SessionAuthState = SessionAuthState.UNAUTHENTICATED
    interaction_mode: InteractionMode = InteractionMode.OWNER_CONTROL
    security_state: SecurityState = SecurityState.OWNER_AUTH_REQUIRED
    domain: str = ""
    read_capability: tuple[str, ...] = ()
    ttl_sec: float = DEFAULT_TTL_SEC
    # NOTE: intentionally NO cookie/token/secret fields — never stored or exposed here.

    def to_public(self) -> dict:
        return {"session_id": self.session_id, "provider": self.provider.value,
                "owner_id": self.owner_id, "created_at": self.created_at,
                "last_active_at": self.last_active_at, "auth_state": self.auth_state.value,
                "interaction_mode": self.interaction_mode.value,
                "security_state": self.security_state.value, "domain": self.domain,
                "read_capability": list(self.read_capability)}


class FinancialBrowserManager:
    """Owns per-provider sessions. On-demand; no persistent browser per provider."""

    def __init__(self, *, ttl_sec: float = DEFAULT_TTL_SEC):
        self._sessions: dict[str, FinancialBrowserSession] = {}
        self._ttl = ttl_sec

    def open(self, provider: Provider, *, owner_id: str = "owner",
             now: float | None = None) -> FinancialBrowserSession:
        now = now if now is not None else time.time()
        pol = POLICIES[provider]
        s = FinancialBrowserSession(
            session_id=f"fbs_{uuid.uuid4().hex[:12]}", provider=provider, owner_id=owner_id,
            created_at=now, last_active_at=now, ttl_sec=self._ttl,
            interaction_mode=pol.default_interaction_mode,
            domain=pol.allowed_domains[0] if pol.allowed_domains else "",
            security_state=SecurityState.OWNER_AUTH_REQUIRED)
        self._sessions[s.session_id] = s
        audit.record(provider=provider.value, actor="OWNER_INPUT", capability="OPEN_SESSION",
                     result="OK", session_id=s.session_id)
        return s

    def get(self, session_id: str, *, now: float | None = None) -> FinancialBrowserSession | None:
        s = self._sessions.get(session_id)
        if s is None:
            return None
        now = now if now is not None else time.time()
        if (now - s.last_active_at) > s.ttl_sec and s.security_state != SecurityState.KILLED:
            s.auth_state = SessionAuthState.OWNER_REAUTH_REQUIRED
            s.security_state = SecurityState.SESSION_EXPIRED
        return s

    def touch(self, session_id: str, *, now: float | None = None) -> None:
        s = self._sessions.get(session_id)
        if s is not None:
            s.last_active_at = now if now is not None else time.time()

    def mark_authenticated(self, session_id: str, *, now: float | None = None
                           ) -> FinancialBrowserSession | None:
        """The OWNER authenticated in-browser (SaathiOS never does). Enables read capability
        per the provider policy; agent still may only READ."""
        s = self._sessions.get(session_id)
        if s is None:
            return None
        pol = POLICIES[s.provider]
        s.auth_state = SessionAuthState.OWNER_AUTHENTICATED
        s.security_state = SecurityState.CONNECTED_READ_ONLY
        s.read_capability = pol.readable_regions
        s.last_active_at = now if now is not None else time.time()
        return s

    def agent_read(self, session_id: str, capability: str) -> tuple[bool, str]:
        """Gate an agent read against policy. Never permits an action; provider-scoped."""
        s = self.get(session_id)
        if s is None:
            return False, "NO_SESSION"
        if s.security_state == SecurityState.KILLED:
            return False, "KILLED"
        if s.auth_state != SessionAuthState.OWNER_AUTHENTICATED:
            audit.record(provider=s.provider.value, actor="AGENT_INPUT", capability=capability,
                         result="BLOCKED", session_id=session_id, detail="not owner-authenticated")
            return False, s.security_state.value
        ok, reason = enforce(Actor.AGENT_INPUT, capability, s.provider)
        audit.record(provider=s.provider.value, actor="AGENT_INPUT", capability=capability,
                     result="OK" if ok else "BLOCKED", session_id=session_id, detail=reason)
        return ok, reason

    def kill(self, session_id: str) -> bool:
        s = self._sessions.get(session_id)
        if s is None:
            return False
        s.security_state = SecurityState.KILLED
        s.read_capability = ()
        s.auth_state = SessionAuthState.UNAUTHENTICATED
        audit.record(provider=s.provider.value, actor="OWNER_INPUT", capability="KILL_SWITCH",
                     result="OK", session_id=session_id)
        return True

    def kill_all(self) -> int:
        n = 0
        for sid in list(self._sessions):
            if self.kill(sid):
                n += 1
        return n

    def list(self) -> list[dict]:
        return [s.to_public() for s in self._sessions.values()]


_MANAGER: FinancialBrowserManager | None = None


def get_manager() -> FinancialBrowserManager:
    global _MANAGER
    if _MANAGER is None:
        _MANAGER = FinancialBrowserManager()
    return _MANAGER
