"""M27 — Canonical governed connector framework.

All external connector communication must go through GovernedConnectorRuntime.
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
from saathi.connectors.gov.registry import ConnectorRegistry, get_registry, reset_registry
from saathi.connectors.gov.runtime import GovernedConnectorRuntime, get_runtime, reset_runtime

__all__ = [
    "AuthMode",
    "ConnectorKind",
    "ConnectorLifecycle",
    "ConnectorManifest",
    "ConnectorPolicy",
    "ConnectorRegistry",
    "ConnectorRequest",
    "ConnectorResult",
    "GovernedConnectorRuntime",
    "get_registry",
    "get_runtime",
    "reset_registry",
    "reset_runtime",
]
