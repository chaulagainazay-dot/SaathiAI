"""M29 — Static built-in connector manifests (no runtime-generated identity).

Adapters are bound separately by GovernedConnectorRuntime; identity lives here.
"""
from __future__ import annotations

from saathi.connectors.gov.models import AuthMode, ConnectorKind, ConnectorManifest


def builtin_manifests() -> list[ConnectorManifest]:
    """Return deterministic built-in manifests for gov.* connectors."""
    return [
        ConnectorManifest(
            connector_id="gov.http",
            version="1.0.0",
            display_name="Governed HTTP",
            description="Governed HTTP adapter (injectable transport; no live SaaS)",
            owner="saathi.connectors.gov",
            kind=ConnectorKind.HTTP,
            adapter_type="http",
            trust_level="LOCAL_NETWORK",
            capability_classes=("HTTP", "READ", "WRITE"),
            capabilities=(
                "http_request", "get", "post", "put", "patch", "delete",
                "health", "validate",
            ),
            supported_operations=(
                "http_request", "get", "post", "put", "patch", "delete",
                "health", "validate",
            ),
            side_effect_classes=("READ_ONLY", "EXTERNAL_MUTATION"),
            required_approvals=("post", "put", "patch", "delete"),
            auth_mode=AuthMode.NONE,
            secret_references=(),
            allowed_domains=("127.0.0.1", "localhost", "example.com"),
            timeout_seconds=10.0,
            max_retries=1,
            retry_policy={"max_retries": 1, "backoff": "none"},
            rate_limit_per_minute=60,
            evidence_policy="redacted",
            incident_policy="m26",
            health_policy={
                "startup_check": "validate",
                "health_check": "health",
                "interval_seconds": 60,
            },
            readiness_policy={
                "readiness_check": "health",
                "requires_lifecycle": ["READY", "DEGRADED"],
            },
            dependencies=(),
            supported_environments=("local", "dev", "test", "staging", "production"),
            rollout_compatible=("OFF", "SHADOW", "CANARY", "ACTIVE", "DRAINING"),
            cloud=False,
            trading=False,
        ),
        ConnectorManifest(
            connector_id="gov.mcp",
            version="1.0.0",
            display_name="Governed MCP",
            description="MCP governance reuse (policy inventory; no live servers)",
            owner="saathi.connectors.gov",
            kind=ConnectorKind.MCP,
            adapter_type="mcp",
            trust_level="LOCAL_SERVICE",
            capability_classes=("MCP", "READ"),
            capabilities=("health", "validate", "status", "inventory"),
            supported_operations=("health", "validate", "status", "inventory"),
            side_effect_classes=("READ_ONLY",),
            required_approvals=(),
            auth_mode=AuthMode.NONE,
            timeout_seconds=10.0,
            max_retries=0,
            retry_policy={"max_retries": 0},
            rate_limit_per_minute=30,
            evidence_policy="redacted",
            incident_policy="m26",
            health_policy={
                "startup_check": "validate",
                "health_check": "health",
            },
            readiness_policy={
                "readiness_check": "status",
                "requires_lifecycle": ["READY", "DEGRADED"],
            },
            # Conceptual: MCP runtime; declared when runtime connector is registered.
            dependencies=(),
            supported_environments=("local", "dev", "test"),
            rollout_compatible=("OFF", "SHADOW", "CANARY", "ACTIVE", "DRAINING"),
        ),
        ConnectorManifest(
            connector_id="gov.browser",
            version="1.0.0",
            display_name="Governed Browser",
            description="Browser governance reuse (domain policy; no live automation accounts)",
            owner="saathi.connectors.gov",
            kind=ConnectorKind.BROWSER,
            adapter_type="browser",
            trust_level="LOCAL_NETWORK",
            capability_classes=("BROWSER", "READ"),
            capabilities=("health", "validate", "policy_check", "navigate"),
            supported_operations=("health", "validate", "policy_check", "navigate"),
            side_effect_classes=("READ_ONLY", "EXTERNAL_MUTATION"),
            required_approvals=("navigate",),
            auth_mode=AuthMode.NONE,
            timeout_seconds=30.0,
            max_retries=0,
            retry_policy={"max_retries": 0},
            rate_limit_per_minute=20,
            evidence_policy="redacted",
            incident_policy="m26",
            health_policy={
                "startup_check": "validate",
                "health_check": "health",
            },
            readiness_policy={
                "readiness_check": "health",
                "requires_lifecycle": ["READY", "DEGRADED"],
            },
            # Conceptual: Browser Gateway; declared when gateway connector is registered.
            dependencies=(),
            supported_environments=("local", "dev", "test"),
            rollout_compatible=("OFF", "SHADOW", "CANARY", "ACTIVE", "DRAINING"),
        ),
        ConnectorManifest(
            connector_id="gov.local_tool",
            version="1.0.0",
            display_name="Governed Local Tool",
            description="Allowlisted local tools only",
            owner="saathi.connectors.gov",
            kind=ConnectorKind.LOCAL_TOOL,
            adapter_type="local_tool",
            trust_level="LOCAL_SYSTEM",
            capability_classes=("LOCAL_TOOL", "EXECUTE", "READ"),
            capabilities=(
                "git_rev_parse", "git_status_short", "python_version",
                "echo_safe", "health", "validate",
            ),
            supported_operations=(
                "git_rev_parse", "git_status_short", "python_version",
                "echo_safe", "health", "validate",
            ),
            side_effect_classes=("READ_ONLY", "LOCAL_MUTATION"),
            required_approvals=(),
            auth_mode=AuthMode.NONE,
            timeout_seconds=15.0,
            max_retries=0,
            retry_policy={"max_retries": 0},
            rate_limit_per_minute=60,
            evidence_policy="redacted",
            incident_policy="m26",
            health_policy={
                "startup_check": "validate",
                "health_check": "health",
            },
            readiness_policy={
                "readiness_check": "health",
                "requires_lifecycle": ["READY", "DEGRADED"],
            },
            dependencies=(),
            supported_environments=("local", "dev", "test"),
            rollout_compatible=("OFF", "SHADOW", "CANARY", "ACTIVE", "DRAINING"),
        ),
    ]


# Logical dependency placeholders (identity-only; not executable connectors)
LOGICAL_DEPENDENCY_IDS = frozenset({
    "gov.browser.gateway",
    "gov.mcp.runtime",
    "gov.http.adapter",
})
