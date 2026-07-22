"""M15 Universal Connector Platform — one governed integration layer.

Canonical connector/tool models, capability catalog, credential references
(metadata only), deterministic + real-local adapters, durable store, and the
gateway-routed ExecutionEngine that is the sole execution boundary. No connector
bypasses the ExecutionGateway; no agent bypasses connector policy.
"""
from saathi.connectors.platform.models import (
    RiskClass, MutationClass, ConnState, ToolDef, ConnectorDef, ToolResult,
    normalized_input_hash, is_executable, APPROVAL_THRESHOLD, MANUAL_ONLY,
)
from saathi.connectors.platform import registry, catalog, credentials, adapters, store
from saathi.connectors.platform.execution import (
    ExecutionEngine, ExecRequest, default_engine,
)

__all__ = [
    "RiskClass", "MutationClass", "ConnState", "ToolDef", "ConnectorDef",
    "ToolResult", "normalized_input_hash", "is_executable", "APPROVAL_THRESHOLD",
    "MANUAL_ONLY", "registry", "catalog", "credentials", "adapters", "store",
    "ExecutionEngine", "ExecRequest", "default_engine",
]
