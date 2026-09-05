"""Credentialless provider session lifecycle.

There is deliberately no authenticating or authenticated state.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from saathi.platform.tg.provider_contracts.errors import (
    ProviderContractError,
    ProviderErrorCode,
)
from saathi.platform.tg.provider_contracts.models import SessionState, TransportKind

TRANSITIONS = {
    SessionState.DISCONNECTED: frozenset({
        SessionState.MOCK_READY,
        SessionState.REPLAY_READY,
        SessionState.UNAVAILABLE,
        SessionState.FAULTED,
        SessionState.CLOSED,
    }),
    SessionState.MOCK_READY: frozenset({
        SessionState.DISCONNECTED,
        SessionState.UNAVAILABLE,
        SessionState.FAULTED,
        SessionState.CLOSED,
    }),
    SessionState.REPLAY_READY: frozenset({
        SessionState.DISCONNECTED,
        SessionState.UNAVAILABLE,
        SessionState.FAULTED,
        SessionState.CLOSED,
    }),
    SessionState.UNAVAILABLE: frozenset({
        SessionState.DISCONNECTED,
        SessionState.FAULTED,
        SessionState.CLOSED,
    }),
    SessionState.FAULTED: frozenset({SessionState.CLOSED}),
    SessionState.CLOSED: frozenset(),
}

FORBIDDEN_SESSION_STATES = frozenset({
    "AUTHENTICATED",
    "LOGGED_IN",
    "ACCOUNT_CONNECTED",
    "BROKER_CONNECTED",
    "LIVE",
    "TRADING_READY",
    "EXECUTION_READY",
})


@dataclass
class ProviderSession:
    provider_id: str
    transport: TransportKind
    state: SessionState = SessionState.DISCONNECTED
    reason: str = ""

    def transition(self, target: SessionState, *, reason: str = "") -> dict[str, Any]:
        if not isinstance(target, SessionState):
            raise ProviderContractError(
                ProviderErrorCode.INVALID_SESSION_STATE,
                "Provider session target is not an allowed offline state",
                details={"target": str(target)},
            )
        if target is self.state:
            return self.snapshot()
        if target not in TRANSITIONS[self.state]:
            raise ProviderContractError(
                ProviderErrorCode.INVALID_SESSION_STATE,
                "Invalid provider session transition",
                details={"from": self.state.value, "to": target.value},
            )
        expected = (
            SessionState.MOCK_READY
            if self.transport is TransportKind.MOCK
            else SessionState.REPLAY_READY
        )
        if target in (SessionState.MOCK_READY, SessionState.REPLAY_READY) and target is not expected:
            raise ProviderContractError(
                ProviderErrorCode.TRANSPORT_FORBIDDEN,
                "Session readiness does not match offline transport",
            )
        self.state = target
        self.reason = reason
        return self.snapshot()

    def snapshot(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "transport": self.transport.value,
            "state": self.state.value,
            "reason": self.reason,
            "authenticated": False,
            "credential_reference": None,
            "network_connection": False,
            "account_access": False,
            "order_execution": False,
            "available_states": [state.value for state in SessionState],
            "forbidden_states": sorted(FORBIDDEN_SESSION_STATES),
            "authentication_state_exists": False,
        }
