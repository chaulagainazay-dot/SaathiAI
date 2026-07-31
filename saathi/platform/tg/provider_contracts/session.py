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
    }),
    SessionState.MOCK_READY: frozenset({
        SessionState.DISCONNECTED,
        SessionState.UNAVAILABLE,
    }),
    SessionState.REPLAY_READY: frozenset({
        SessionState.DISCONNECTED,
        SessionState.UNAVAILABLE,
    }),
    SessionState.UNAVAILABLE: frozenset({SessionState.DISCONNECTED}),
}


@dataclass
class ProviderSession:
    provider_id: str
    transport: TransportKind
    state: SessionState = SessionState.DISCONNECTED
    reason: str = ""

    def transition(self, target: SessionState, *, reason: str = "") -> dict[str, Any]:
        if target is self.state:
            return self.snapshot()
        if target not in TRANSITIONS[self.state]:
            raise ProviderContractError(
                ProviderErrorCode.CONTRACT_VIOLATION,
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
            "available_states": [state.value for state in SessionState],
        }
