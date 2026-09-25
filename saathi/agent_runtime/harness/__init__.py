"""FM-I1+ — AgentHarness contract, FakeInMemoryHarness, LocalModelHarness, controller.

Internal platform multi-turn driver proof under ``saathi.agent_runtime``.

This package is **non-production** and **internal-only**. It does not:

* integrate commercial CLIs or cloud providers;
* replace ExecutionGateway, approvals, RBAC, or Trading Guardian;
* wrap or implement engineering ``AgentSessionAdapter``;
* introduce a shared DriverProtocol or public SDK;
* start/stop/kill Ollama or pull models (LocalModelHarness is user-managed only).

Authority model (Alternative F / FM-C2):

* ``RunState`` remains authoritative for platform multi-agent runs.
* Harness session state is a **projection** only.
* Harnesses propose tools; only the trusted controller builds ToolIntent.
* FakeInMemoryHarness is fully in-process and deterministic.
* LocalModelHarness (FM-I6) is an untrusted local inference driver only.
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
from saathi.agent_runtime.harness.gateway_bridge import (
    RealExecutionGatewayAdapter,
    build_isolated_execution_gateway,
)
from saathi.agent_runtime.harness.durable_store import HarnessDurableStore
from saathi.agent_runtime.harness.persistence import (
    SCHEMA_VERSION,
    SOURCE_OF_TRUTH,
    DurableEventRecord,
    DurableSessionRecord,
    RecoveryDisposition,
    RecoveryResult,
    RetentionClass,
    TerminalOutcome,
)
from saathi.agent_runtime.harness.audit import HarnessAuditLog, HarnessAuditRecord
from saathi.agent_runtime.harness.types import can_transition_harness, is_terminal_harness_state
from saathi.agent_runtime.harness.governance import (
    AdmissionRequest,
    AdmissionResult,
    HarnessSessionGovernor,
)
from saathi.agent_runtime.harness.governance_policy import (
    AdmissionDecision,
    HarnessAdmissionPolicy,
    HarnessQueuePolicy,
    HarnessResourcePolicy,
    HarnessTimeoutPolicy,
    QueueEntryState,
)
from saathi.agent_runtime.harness.local_model import LocalModelHarness
from saathi.agent_runtime.harness.local_model_types import (
    LocalModelConfig,
    LocalReadinessState,
    PINNED_MODEL,
    PINNED_MODEL_DIGEST,
    ALLOWED_ENDPOINT,
    validate_loopback_endpoint,
)
from saathi.agent_runtime.harness.local_model_transport import (
    MockOllamaTransport,
    LoopbackOllamaTransport,
    MockScript,
    TransportError,
)

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
    "RealExecutionGatewayAdapter",
    "build_isolated_execution_gateway",
    "HarnessDurableStore",
    "SCHEMA_VERSION",
    "SOURCE_OF_TRUTH",
    "DurableEventRecord",
    "DurableSessionRecord",
    "RecoveryDisposition",
    "RecoveryResult",
    "RetentionClass",
    "TerminalOutcome",
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
    "AdmissionRequest",
    "AdmissionResult",
    "HarnessSessionGovernor",
    "AdmissionDecision",
    "HarnessAdmissionPolicy",
    "HarnessQueuePolicy",
    "HarnessResourcePolicy",
    "HarnessTimeoutPolicy",
    "QueueEntryState",
    "LocalModelHarness",
    "LocalModelConfig",
    "LocalReadinessState",
    "MockOllamaTransport",
    "LoopbackOllamaTransport",
    "MockScript",
    "TransportError",
    "PINNED_MODEL",
    "PINNED_MODEL_DIGEST",
    "ALLOWED_ENDPOINT",
    "validate_loopback_endpoint",
]

# Intentionally not production-certified (FM-I1 through FM-I6).
PRODUCTION_CERTIFIED = False
MILESTONE = "FM-I6"
PROTOCOL_VERSION = "1.0"
