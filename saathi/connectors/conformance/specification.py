"""M30 — Canonical connector conformance specification (check catalog)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from saathi.connectors.conformance.models import (
    CONFORMANCE_SPEC_VERSION,
    CheckCategory,
    CheckSeverity,
)


@dataclass(frozen=True)
class CheckDef:
    check_id: str
    category: CheckCategory
    severity: CheckSeverity
    required: bool
    summary: str
    applies_to: tuple[str, ...] = ()  # empty = all builtins


# Catalog of checks — assessor implements runners keyed by check_id
SPEC_CHECKS: tuple[CheckDef, ...] = (
    # Shared
    CheckDef("manifest.identity", CheckCategory.MANIFEST, CheckSeverity.MANDATORY, True, "Manifest identity present and valid"),
    CheckDef("manifest.version", CheckCategory.MANIFEST, CheckSeverity.MANDATORY, True, "Manifest version declared"),
    CheckDef("identity.registry_resolve", CheckCategory.IDENTITY, CheckSeverity.CRITICAL, True, "Registry resolve-only identity"),
    CheckDef("identity.unknown_denied", CheckCategory.IDENTITY, CheckSeverity.CRITICAL, True, "Unknown connector denied"),
    CheckDef("capabilities.declared_only", CheckCategory.CAPABILITIES, CheckSeverity.MANDATORY, True, "Undeclared operations denied"),
    CheckDef("trust.level_present", CheckCategory.TRUST, CheckSeverity.MANDATORY, True, "Trust level declared"),
    CheckDef("trust.prohibited_blocked", CheckCategory.TRUST, CheckSeverity.CRITICAL, True, "PROHIBITED cannot execute"),
    CheckDef("policy.domain", CheckCategory.POLICY, CheckSeverity.MANDATORY, True, "Domain policy enforced", ("gov.http", "gov.browser")),
    CheckDef("policy.https_remote", CheckCategory.POLICY, CheckSeverity.CRITICAL, True, "HTTPS required for remote", ("gov.http",)),
    CheckDef("approval.external_mutation", CheckCategory.APPROVAL, CheckSeverity.CRITICAL, True, "External mutation requires approval"),
    CheckDef("approval.caller_no_authority", CheckCategory.APPROVAL, CheckSeverity.CRITICAL, True, "Caller identity alone grants no authority"),
    CheckDef("approval.no_rollout_bypass", CheckCategory.APPROVAL, CheckSeverity.CRITICAL, True, "Approval cannot bypass rollout OFF"),
    CheckDef("approval.no_cert_bypass", CheckCategory.APPROVAL, CheckSeverity.CRITICAL, True, "Approval cannot bypass certification"),
    CheckDef("approval.expired_fails", CheckCategory.APPROVAL, CheckSeverity.MANDATORY, True, "Expired approval fails"),
    CheckDef("approval.payload_bind", CheckCategory.APPROVAL, CheckSeverity.MANDATORY, True, "Altered payload invalidates approval"),
    CheckDef("rollout.off_no_exec", CheckCategory.ROLLOUT, CheckSeverity.CRITICAL, True, "OFF performs no adapter execution"),
    CheckDef("rollout.shadow_no_side_effect", CheckCategory.ROLLOUT, CheckSeverity.CRITICAL, True, "SHADOW no external side effect"),
    CheckDef("rollout.canary_deterministic", CheckCategory.ROLLOUT, CheckSeverity.MANDATORY, True, "CANARY selection deterministic"),
    CheckDef("rollout.active_requires_prod_cert", CheckCategory.ROLLOUT, CheckSeverity.CRITICAL, True, "ACTIVE requires production certification"),
    CheckDef("rollout.active_requires_connector_cert", CheckCategory.ROLLOUT, CheckSeverity.CRITICAL, True, "ACTIVE requires connector certification"),
    CheckDef("rollout.draining_blocks_new", CheckCategory.ROLLOUT, CheckSeverity.MANDATORY, True, "DRAINING blocks new work"),
    CheckDef("adapter.contract", CheckCategory.ADAPTER_CONTRACT, CheckSeverity.MANDATORY, True, "Adapter implements execute contract"),
    CheckDef("input.schema", CheckCategory.INPUT_VALIDATION, CheckSeverity.MANDATORY, True, "Invalid input rejected"),
    CheckDef("output.redacted", CheckCategory.OUTPUT_VALIDATION, CheckSeverity.CRITICAL, True, "Output redacted / privacy_safe"),
    CheckDef("timeout.bounded", CheckCategory.TIMEOUT, CheckSeverity.MANDATORY, True, "Timeout fails safely"),
    CheckDef("retry.bounded", CheckCategory.RETRY, CheckSeverity.MANDATORY, True, "Retry bounded by manifest"),
    CheckDef("rate_limit.enforced", CheckCategory.RATE_LIMIT, CheckSeverity.MANDATORY, True, "Rate limit enforced"),
    CheckDef("idempotency.conflict", CheckCategory.IDEMPOTENCY, CheckSeverity.MANDATORY, True, "Idempotency conflict detected"),
    CheckDef("health.distinct", CheckCategory.HEALTH, CheckSeverity.MANDATORY, True, "Health check runs"),
    CheckDef("readiness.not_import_alone", CheckCategory.READINESS, CheckSeverity.MANDATORY, True, "Readiness distinct from import"),
    CheckDef("dependencies.graph", CheckCategory.DEPENDENCIES, CheckSeverity.MANDATORY, True, "Dependency graph valid"),
    CheckDef("evidence.written", CheckCategory.EVIDENCE, CheckSeverity.MANDATORY, True, "Evidence written without secrets"),
    CheckDef("redaction.secrets", CheckCategory.REDACTION, CheckSeverity.CRITICAL, True, "Secrets redacted from evidence"),
    CheckDef("incidents.dedup", CheckCategory.INCIDENTS, CheckSeverity.LIMITATION, False, "Incident dedup behavior"),
    CheckDef("failure.timeout", CheckCategory.FAILURE_RECOVERY, CheckSeverity.MANDATORY, True, "Timeout failure injection safe"),
    CheckDef("failure.connection", CheckCategory.FAILURE_RECOVERY, CheckSeverity.MANDATORY, True, "Connection failure injection safe"),
    CheckDef("direct_access.blocked", CheckCategory.DIRECT_ACCESS, CheckSeverity.CRITICAL, True, "Direct provider bypass blocked"),
    CheckDef("side_effect.financial_blocked", CheckCategory.SIDE_EFFECT_SAFETY, CheckSeverity.CRITICAL, True, "Financial ops blocked"),
    CheckDef("side_effect.trading_blocked", CheckCategory.SIDE_EFFECT_SAFETY, CheckSeverity.CRITICAL, True, "Trading ops blocked"),
    CheckDef("resource.payload_size", CheckCategory.RESOURCE_SAFETY, CheckSeverity.MANDATORY, True, "Oversized payload rejected"),
    # HTTP-specific
    CheckDef("http.methods_allow", CheckCategory.ADAPTER_CONTRACT, CheckSeverity.MANDATORY, True, "Allowed HTTP methods", ("gov.http",)),
    CheckDef("http.methods_deny", CheckCategory.ADAPTER_CONTRACT, CheckSeverity.MANDATORY, True, "Denied HTTP methods", ("gov.http",)),
    CheckDef("http.loopback_ok", CheckCategory.ADAPTER_CONTRACT, CheckSeverity.MANDATORY, True, "Loopback execution", ("gov.http",)),
    CheckDef("http.auth_header_stripped", CheckCategory.REDACTION, CheckSeverity.CRITICAL, True, "Authorization header stripped", ("gov.http",)),
    CheckDef("http.query_secret_policy", CheckCategory.REDACTION, CheckSeverity.MANDATORY, True, "Secret payload keys denied", ("gov.http",)),
    # MCP-specific
    CheckDef("mcp.unknown_tool", CheckCategory.ADAPTER_CONTRACT, CheckSeverity.MANDATORY, True, "Unknown MCP tool denied", ("gov.mcp",)),
    CheckDef("mcp.inventory", CheckCategory.ADAPTER_CONTRACT, CheckSeverity.MANDATORY, True, "MCP inventory path", ("gov.mcp",)),
    CheckDef("mcp.no_arbitrary_server", CheckCategory.DIRECT_ACCESS, CheckSeverity.CRITICAL, True, "No arbitrary MCP server", ("gov.mcp",)),
    # Browser-specific
    CheckDef("browser.domain", CheckCategory.POLICY, CheckSeverity.MANDATORY, True, "Browser domain policy", ("gov.browser",)),
    CheckDef("browser.dry_run", CheckCategory.ADAPTER_CONTRACT, CheckSeverity.MANDATORY, True, "Browser dry-run / no live login", ("gov.browser",)),
    CheckDef("browser.nav_approval", CheckCategory.APPROVAL, CheckSeverity.MANDATORY, True, "Navigate requires approval path", ("gov.browser",)),
    # Local tool-specific
    CheckDef("local.allowlist", CheckCategory.ADAPTER_CONTRACT, CheckSeverity.CRITICAL, True, "Executable allowlist", ("gov.local_tool",)),
    CheckDef("local.no_shell", CheckCategory.DIRECT_ACCESS, CheckSeverity.CRITICAL, True, "shell=True impossible", ("gov.local_tool",)),
    CheckDef("local.arbitrary_path_denied", CheckCategory.ADAPTER_CONTRACT, CheckSeverity.CRITICAL, True, "Arbitrary path denied", ("gov.local_tool",)),
    CheckDef("local.trading_cmd_denied", CheckCategory.SIDE_EFFECT_SAFETY, CheckSeverity.CRITICAL, True, "Trading/financial cmds denied", ("gov.local_tool",)),
)


def checks_for(connector_id: str) -> list[CheckDef]:
    out = []
    for c in SPEC_CHECKS:
        if not c.applies_to or connector_id in c.applies_to:
            out.append(c)
    return out


def specification_document() -> dict[str, Any]:
    return {
        "schema": "m30.conformance_specification.v1",
        "version": CONFORMANCE_SPEC_VERSION,
        "categories": [c.value for c in CheckCategory],
        "statuses": ["PASS", "FAIL", "BLOCKED", "SKIPPED", "NOT_APPLICABLE"],
        "states": [
            "UNASSESSED", "ASSESSING", "CERTIFIED", "CERTIFIED_WITH_LIMITATIONS",
            "FAILED", "ENVIRONMENT_BLOCKED", "STALE", "REVOKED",
        ],
        "checks": [
            {
                "check_id": c.check_id,
                "category": c.category.value,
                "severity": c.severity.value,
                "required": c.required,
                "summary": c.summary,
                "applies_to": list(c.applies_to) or ["*"],
            }
            for c in SPEC_CHECKS
        ],
        "privacy_safe": True,
    }
