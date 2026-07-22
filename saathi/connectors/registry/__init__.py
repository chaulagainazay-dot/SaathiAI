"""M29 — Canonical connector identity, trust model, and registry API.

Defines *what a connector is*. Live SaaS integrations are out of scope.

Canonical path remains:

    Caller → ToolIntent → ExecutionGateway → GovernedConnectorRuntime → adapter

This package owns identity/trust/manifest validation and the
``python -m saathi.connectors.registry`` documentation CLI.
It does **not** reimplement runtime, rollout, approval, evidence, or adapters.
"""
from __future__ import annotations

from saathi.connectors.registry.trust import (
    TRUST_ORDER,
    TrustLevel,
    approval_floor_for_trust,
    capabilities_allowed_for_trust,
    enforce_capabilities_for_trust,
    rollout_eligible_for_trust,
)
from saathi.connectors.registry.capabilities import (
    ConnectorCapability,
    capability_exceeds_trust,
    normalize_capability_classes,
)
from saathi.connectors.registry.validation import (
    ManifestValidationError,
    ManifestValidationResult,
    validate_manifest,
)
from saathi.connectors.registry.deps import (
    DependencyCycleError,
    DependencyError,
    validate_dependency_graph,
)
from saathi.connectors.registry.docs import generate_registry_docs
from saathi.connectors.registry.persistence import (
    RegistryPersistence,
    load_registry_snapshot,
    save_registry_snapshot,
)
from saathi.connectors.gov.registry import (
    ConnectorRegistry,
    get_registry,
    reset_registry,
)
from saathi.connectors.gov.models import ConnectorManifest

__all__ = [
    "TrustLevel",
    "TRUST_ORDER",
    "ConnectorCapability",
    "ManifestValidationError",
    "ManifestValidationResult",
    "DependencyCycleError",
    "DependencyError",
    "ConnectorRegistry",
    "ConnectorManifest",
    "RegistryPersistence",
    "approval_floor_for_trust",
    "capabilities_allowed_for_trust",
    "capability_exceeds_trust",
    "enforce_capabilities_for_trust",
    "generate_registry_docs",
    "get_registry",
    "load_registry_snapshot",
    "normalize_capability_classes",
    "reset_registry",
    "rollout_eligible_for_trust",
    "save_registry_snapshot",
    "validate_dependency_graph",
    "validate_manifest",
]
