"""AgentHarness protocol — internal multi-turn driver contract (FM-I1).

Implementations are untrusted drivers. They must never authorize, approve,
store credentials, or execute tools. Platform mediation is mandatory.
"""
from __future__ import annotations

from typing import Iterator, List, Protocol, runtime_checkable

from saathi.agent_runtime.harness.types import (
    CancelAck,
    HarnessCapabilityProfile,
    HarnessEvent,
    HarnessHealth,
    HarnessResourceUsage,
    HarnessSessionHandle,
    HarnessSessionStartRequest,
    HarnessTurnHandle,
    HarnessTurnSubmitRequest,
    SessionCloseResult,
)


@runtime_checkable
class AgentHarness(Protocol):
    """Minimal internal AgentHarness contract (M385 D6/D9; FM-I1 scope)."""

    def describe_capabilities(self) -> HarnessCapabilityProfile:
        """Return descriptive capability profile (never grants permission)."""
        ...

    def start_session(self, req: HarnessSessionStartRequest) -> HarnessSessionHandle:
        """Create harness-local session bound to platform-minted identifiers."""
        ...

    def submit_turn(self, req: HarnessTurnSubmitRequest) -> HarnessTurnHandle:
        """Submit a turn; start deterministic/scripted driver work."""
        ...

    def stream_events(self, session_id: str, after_seq: int = 0) -> Iterator[HarnessEvent]:
        """Yield ordered events with sequence_number > after_seq."""
        ...

    def poll_events(self, session_id: str, after_seq: int = 0) -> List[HarnessEvent]:
        """Deterministic poll of durable in-memory events."""
        ...

    def request_cancel(self, session_id: str, reason: str) -> CancelAck:
        """Cooperative cancel; fail-closed if not acknowledged."""
        ...

    def close_session(self, session_id: str, reason: str = "") -> SessionCloseResult:
        """Release resources; idempotent on already-closed sessions."""
        ...

    def health(self) -> HarnessHealth:
        """Liveness without secrets."""
        ...

    def resource_usage(self, session_id: str) -> HarnessResourceUsage:
        """Bounded fake resource accounting for a session."""
        ...
