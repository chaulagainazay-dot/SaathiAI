"""FM-I1 — AgentHarness contract, FakeInMemoryHarness, HarnessSessionController.

Internal platform multi-turn driver proof under ``saathi.agent_runtime``.

This package is **non-production** and **internal-only**. It does not:

* integrate commercial CLIs, providers, Ollama, or network services;
* replace ExecutionGateway, approvals, RBAC, or Trading Guardian;
* wrap or implement engineering ``AgentSessionAdapter``;
* introduce a shared DriverProtocol or public SDK.

Authority model (Alternative F / FM-C2):

* ``RunState`` remains authoritative for platform multi-agent runs.
* Harness session state is a **projection** only.
* Harnesses propose tools; only the trusted controller builds ToolIntent.
* FakeInMemoryHarness is fully in-process and deterministic.
"""
from __future__ import annotations

from saathi.agent_runtime.harness.types import (
    ApprovalRefState,
    CancelAck,
    CancelAckStatus,
    EventClassification,
    EventRedactionState,
    HarnessBudget,
    HarnessCapability,
    HarnessCapabilityId,
    HarnessCapabilityProfile,
    HarnessEvent,
    HarnessEventType,
    HarnessHealth,
    HarnessHealthStatus,
    HarnessResourceUsage,
    HarnessSessionHandle,
    HarnessSessionStartRequest,
    HarnessSessionState,
    HarnessTurnHandle,
    HarnessTurnSubmitRequest,
    ProtocolViolationKind,
    SessionCloseResult,
    ToolProposal,
    ToolProposalDisposition,
)
from saathi.agent_runtime.harness.errors import (
    HarnessError,
    HarnessErrorCode,
)
from saathi.agent_runtime.harness.protocol import AgentHarness
from saathi.agent_runtime.harness.mapping import (
    HARNESS_TO_RUN_STATE,
    project_harness_to_run_state,
)
from saathi.agent_runtime.harness.fake import FakeInMemoryHarness, FakeScenario
from saathi.agent_runtime.harness.controller import (
    GatewayTestDouble,
    HarnessSessionController,
    MediatedToolResult,
)
from saathi.agent_runtime.harness.audit import HarnessAuditLog, HarnessAuditRecord
from saathi.agent_runtime.harness.types import can_transition_harness, is_terminal_harness_state

__all__ = [
    "AgentHarness",
    "ApprovalRefState",
    "CancelAck",
    "CancelAckStatus",
    "EventClassification",
    "EventRedactionState",
    "FakeInMemoryHarness",
    "FakeScenario",
    "GatewayTestDouble",
    "HARNESS_TO_RUN_STATE",
    "HarnessAuditLog",
    "HarnessAuditRecord",
    "HarnessBudget",
    "HarnessCapability",
    "HarnessCapabilityId",
    "HarnessCapabilityProfile",
    "HarnessError",
    "HarnessErrorCode",
    "HarnessEvent",
    "HarnessEventType",
    "HarnessHealth",
    "HarnessHealthStatus",
    "HarnessResourceUsage",
    "HarnessSessionController",
    "HarnessSessionHandle",
    "HarnessSessionStartRequest",
    "HarnessSessionState",
    "HarnessTurnHandle",
    "HarnessTurnSubmitRequest",
    "MediatedToolResult",
    "ProtocolViolationKind",
    "SessionCloseResult",
    "ToolProposal",
    "ToolProposalDisposition",
    "project_harness_to_run_state",
    "can_transition_harness",
    "is_terminal_harness_state",
]

# FM-I1 is intentionally not production-certified.
PRODUCTION_CERTIFIED = False
MILESTONE = "FM-I1"
PROTOCOL_VERSION = "1.0"
