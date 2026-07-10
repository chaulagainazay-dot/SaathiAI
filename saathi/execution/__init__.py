"""saathi.execution — unified execution subsystem public API.

This package hosts TWO cooperating execution concerns that historically
collided on the name ``saathi.execution``:

1. **Trade execution** (finance): the M5 governed, paper-first order layer
   (``ExecutionIntent`` -> broker ``Connector`` -> ``ExecutionService``).
   Source: :mod:`saathi.execution.trade` (formerly ``saathi/execution.py``).

2. **Universal Secure Execution Layer** (ToolIntent gateway): the ADR
   ExecutionGateway pipeline for side-effecting tool calls
   (``ToolIntent`` -> validate -> authorize -> risk -> approve -> execute ->
   sanitize -> evidence). Source: :mod:`saathi.execution.gateway` and siblings.

Name-collision resolution (documented, reversible):
    ``ExecutionStatus`` is exported as the **finance** order-status enum, to
    preserve the pre-existing, tested finance API used by
    ``tests/test_execution.py``, ``tests/test_trade_journal.py`` and
    ``tests/test_m5_explainability.py``. The gateway's result-status enum is
    exported as ``ToolExecutionStatus``. All other gateway symbols keep their
    canonical names. ``RiskLevel`` refers to the gateway/state enum used by the
    ExecutionGateway pipeline (the ToolIntent-local risk hint remains available
    as :class:`saathi.execution.toolintent.RiskLevel`).
"""

# --- Trade execution (finance) — original owner of the bare names ----------
from saathi.execution.trade import (
    ExecutionSide,
    OrderType,
    ExecutionStatus,          # finance order status (bare name preserved)
    ExecutionIntent,
    OrderPreview,
    ExecutionOrder,
    BrokerConnector,
    PaperConnector,
    ReplayConnector,
    BrokerRegistry,
    ExecutionService,
)

# --- Universal Secure Execution Layer (ToolIntent gateway) -----------------
from saathi.execution.toolintent import (
    ToolIntent,
    ActorType,
    ApprovalLevel,
    Priority,
    BusinessUnit,
)
from saathi.execution.gateway import ExecutionGateway, ExecutionContext
from saathi.execution.results import (
    ExecutionResult,
    SanitizedResult,
    Evidence,
    AuditTrail,
    ExecutionStatus as ToolExecutionStatus,   # gateway result status (namespaced)
)
from saathi.execution.state import (
    IntentState,
    RiskLevel,                 # gateway/pipeline risk level
    ApprovalStatus,
    StateTransition,
    StateHistory,
)
from saathi.execution.errors import (
    ExecutionError,
    ErrorSeverity,
    ExecutionGatewayException,
    ValidationException,
    AuthorizationException,
    ApprovalException,
    CredentialException,
    ConnectorException,
    ResultException,
    StateException,
)

# Repair 1 mandated alias: approval decision surface.
ApprovalDecision = ApprovalStatus

__all__ = [
    # Trade execution (finance)
    "ExecutionSide",
    "OrderType",
    "ExecutionStatus",
    "ExecutionIntent",
    "OrderPreview",
    "ExecutionOrder",
    "BrokerConnector",
    "PaperConnector",
    "ReplayConnector",
    "BrokerRegistry",
    "ExecutionService",
    # ToolIntent gateway
    "ToolIntent",
    "ActorType",
    "ApprovalLevel",
    "Priority",
    "BusinessUnit",
    "ExecutionGateway",
    "ExecutionContext",
    "ExecutionResult",
    "SanitizedResult",
    "Evidence",
    "AuditTrail",
    "ToolExecutionStatus",
    "IntentState",
    "RiskLevel",
    "ApprovalStatus",
    "ApprovalDecision",
    "StateTransition",
    "StateHistory",
    # Errors
    "ExecutionError",
    "ErrorSeverity",
    "ExecutionGatewayException",
    "ValidationException",
    "AuthorizationException",
    "ApprovalException",
    "CredentialException",
    "ConnectorException",
    "ResultException",
    "StateException",
]
