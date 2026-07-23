"""M49.4 closure audits — registry, gateway, residual, shell, authority."""
from __future__ import annotations

from saathi.tool_runtime.closure_audit import (
    audit_authority_closure,
    audit_compatibility_bridge,
    audit_idempotency_closure,
    audit_reachability_negative,
    audit_residual_legacy_handlers,
    audit_shell_closure,
    m49_4_full_closure_report,
    validate_registry_closure,
)
from saathi.tool_runtime.gateway_audit import (
    audit_cancellation,
    audit_connectors,
    validate_tool_gateway_coverage,
)
from saathi.tool_runtime.registry import reset_registry_for_tests


def test_registry_closure_pass():
    reset_registry_for_tests()
    report = validate_registry_closure()
    assert report["status"] == "PASS"
    assert report["ok"] is True
    assert report["adapter_parity"] is True
    assert report["duplicate_tool_ids"] == []
    assert report["manifest_count"] >= 20


def test_gateway_closure_enforced():
    reset_registry_for_tests()
    report = validate_tool_gateway_coverage()
    assert report["critical_count"] == 0
    assert report["status"] == "PASS"
    assert report["gateway_state"] == "TOOL_GATEWAY_ENFORCED"
    assert report["freeform_shell_state"] == "FREEFORM_SHELL_BLOCKED"


def test_residual_legacy_census_no_unknown():
    residual = audit_residual_legacy_handlers()
    assert residual["unknown_count"] == 0
    assert residual["handler_count"] == 120
    assert residual["outside_explicit_policy_sets"] == []
    assert residual["legacy_state"] == "LEGACY_RUNTIME_BOUNDED"
    assert residual["by_closure_decision"].get("RETAIN_BOUNDED_WITH_REASON", 0) == 59
    assert residual["by_closure_decision"].get("DEFERRED_DISABLED", 0) == 47
    assert residual["by_closure_decision"].get("CANONICAL_WRAPPER", 0) == 11
    assert residual["by_closure_decision"].get("PROHIBITED", 0) == 3


def test_reachability_negative_proof():
    proof = audit_reachability_negative()
    assert proof["status"] == "PASS"
    assert proof["failures"] == []
    assert proof["samples"]["run_shell"]["blocked"] is True
    assert proof["samples"]["ab_goto"]["blocked"] is True


def test_compatibility_bridge_allowlist_only():
    bridge = audit_compatibility_bridge()
    assert bridge["status"] == "PASS"
    assert bridge["unknown_returns_none"] is True
    assert bridge["manage_tasks_mutate_blocked"] is True
    assert bridge["mapped_count"] == 11
    assert bridge["bridge_decision"] == "RETAIN_TEMPORARILY"


def test_shell_closure():
    shell = audit_shell_closure()
    assert shell["status"] == "PASS"
    assert shell["freeform_shell_state"] == "FREEFORM_SHELL_BLOCKED"
    assert shell["allowlisted_subprocess_count"] == 7
    assert shell["run_shell_direct_blocked"] is True
    assert shell["project_run_direct_blocked"] is True


def test_connector_closure():
    reset_registry_for_tests()
    c = audit_connectors()
    assert c["status"] == "PASS"
    assert c["connector_actions"] == 11
    assert c["mutation_mode"] == "DRY_RUN_ONLY"
    assert c["generic_connector_execution"] == "ABSENT"


def test_cancellation_no_unknown():
    reset_registry_for_tests()
    c = audit_cancellation()
    assert c["status"] == "PASS"
    assert c["unknown_count"] == 0


def test_idempotency_single_host_classification():
    idem = audit_idempotency_closure()
    assert idem["status"] == "PASS"
    assert idem["single_host_classification"] == "SINGLE_HOST_SAFE"
    assert idem["multi_host_classification"] == "MULTI_HOST_UNSAFE"


def test_authority_fail_closed():
    auth = audit_authority_closure()
    assert auth["status"] == "PASS"
    assert auth["authority_state"] == "AUTHORITY_FAIL_CLOSED"
    assert auth["financial_execution_blocked"] is True
    assert auth["caller_authority_override"] == "REJECTED"


def test_full_closure_report_aggregates():
    reset_registry_for_tests()
    report = m49_4_full_closure_report()
    assert report["milestone"] == "M49.4"
    assert report["overall_status"] in ("PASS", "PARTIAL")
    assert report["blocked_sections"] == []
    assert report["states"]["gateway"] == "TOOL_GATEWAY_ENFORCED"
    assert report["states"]["legacy"] == "LEGACY_RUNTIME_BOUNDED"
    assert report["states"]["shell"] == "FREEFORM_SHELL_BLOCKED"
    assert report["states"]["production"] == "PRODUCTION_NOT_AUTHORIZED"
    assert report["core_question_answer"] in ("YES_WITH_LIMITATIONS", "YES")
    assert report["counts"]["legacy_handlers"] == 120
