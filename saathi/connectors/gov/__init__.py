"""M27/M28/M29 — Canonical governed connector framework.

All production connector execution:

    Caller → ToolIntent → ExecutionGateway → GovernedConnectorRuntime → adapter

M29 adds canonical manifest identity, trust model, and registry resolution.
Reuses M26 rollout/incidents, M25 certification, mcp_governance, and browser policy.
Does not enable cloud inference or live accounts.
"""
from saathi.connectors.gov.models import (
    AuthMode,
    ConnectorKind,
    ConnectorLifecycle,
    ConnectorManifest,
    ConnectorRequest,
    ConnectorResult,
)
from saathi.connectors.gov.policy import ConnectorPolicy
from saathi.connectors.gov.registry import (
    ConnectorRegistry,
    DuplicateConnectorError,
    UnknownConnectorError,
    get_registry,
    reset_registry,
)
from saathi.connectors.gov.runtime import GovernedConnectorRuntime, get_runtime, reset_runtime
from saathi.connectors.gov.side_effects import SideEffectClass, classify_operation, evaluate_side_effect
from saathi.connectors.gov.gateway_bridge import execute_via_gateway, ensure_default_connector_handler
from saathi.connectors.gov.bypass_guard import scan_connector_bypasses

__all__ = [
    "AuthMode",
    "ConnectorKind",
    "ConnectorLifecycle",
    "ConnectorManifest",
    "ConnectorPolicy",
    "ConnectorRegistry",
    "ConnectorRequest",
    "ConnectorResult",
    "DuplicateConnectorError",
    "UnknownConnectorError",
    "GovernedConnectorRuntime",
    "SideEffectClass",
    "classify_operation",
    "evaluate_side_effect",
    "execute_via_gateway",
    "ensure_default_connector_handler",
    "scan_connector_bypasses",
    "get_registry",
    "get_runtime",
    "reset_registry",
    "reset_runtime",
]
