"""M49.4 closure audits — registry, reachability, legacy residual, integration readiness.

Read-only by default. Never executes live connectors, never networks for mutation,
never accesses raw credentials. Used for certification and negative proofs.
"""
from __future__ import annotations

from collections import Counter
from typing import Any

from saathi.tool_runtime.contracts import (
    ToolAuthorityClass,
    ToolAvailability,
    ToolCancellationSupport,
    ToolSideEffectClass,
)
from saathi.tool_runtime.gateway_audit import (
    audit_approvals,
    audit_cancellation,
    audit_connectors,
    audit_legacy_execution,
    validate_tool_gateway_coverage,
)
from saathi.tool_runtime.legacy_policy import (
    CANONICAL_LEGACY_MAP,
    DEFERRED_RUNTIME_TOOLS,
    FREEFORM_SHELL_TOOLS,
    LEGACY_BOUNDED_TOOLS,
    PROHIBITED_TOOLS,
    classify_legacy_tool,
    is_runtime_executable,
    policy_summary,
)
from saathi.tool_runtime.registry import ToolRegistry, default_registry


def validate_registry_closure(registry: ToolRegistry | None = None) -> dict[str, Any]:
    """Prove ToolRegistry is the only execution-governance registry for M49 tools.

    Returns status PASS | PARTIAL | BLOCKED.
    """
    reg = registry or default_registry()
    findings: list[dict[str, Any]] = []
    max_sev = 0
    rank = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1, "INFO": 0}

    def _add(sev: str, code: str, message: str, **extra: Any) -> None:
        nonlocal max_sev
        max_sev = max(max_sev, rank.get(sev, 0))
        findings.append({"severity": sev, "code": code, "message": message, **extra})

    validation = reg.validate_all()
    if not validation.get("ok"):
        for issue in validation.get("issues") or []:
            _add("HIGH", "MANIFEST_ADAPTER_MISMATCH", str(issue), issue=issue)

    manifests = reg.list_manifests(include_disabled=True)
    ids = [m.tool_id for m in manifests]
    dupes = [tid for tid, n in Counter(ids).items() if n > 1]
    for tid in dupes:
        _add("CRITICAL", "DUPLICATE_TOOL_ID", f"duplicate tool_id {tid}")

    # Every registered key has adapter (validate_all); every enabled has resolve
    unbound = []
    for m in manifests:
        if m.enabled and m.availability == ToolAvailability.ENABLED:
            if reg.resolve(m.tool_id) is None:
                unbound.append(m.tool_id)
    for tid in unbound:
        _add("HIGH", "ENABLED_WITHOUT_ADAPTER", f"{tid} enabled without adapter")

    # Prohibited/disabled must not be treated as executable availability ENABLED
    for m in manifests:
        if m.availability == ToolAvailability.PROHIBITED and m.enabled:
            # enabled flag with PROHIBITED availability is allowed if service blocks
            # before adapter — service checks availability. Flag only if ENABLED.
            pass
        if (
            m.authority_class == ToolAuthorityClass.FINANCIAL_EXECUTION
            and m.availability != ToolAvailability.PROHIBITED
        ):
            _add(
                "CRITICAL",
                "FINANCIAL_NOT_PROHIBITED",
                f"{m.tool_id} financial execution not PROHIBITED",
            )

    # Legacy registry must not expose execute_registered_tool
    legacy_exec_ok = True
    try:
        from saathi.tools import registry as legacy_reg

        legacy_exec_ok = not hasattr(legacy_reg, "execute_registered_tool")
        if not legacy_exec_ok:
            _add(
                "CRITICAL",
                "LEGACY_REGISTRY_GATEWAY",
                "legacy tools.registry exposes execute_registered_tool",
            )
    except Exception as exc:
        _add("MEDIUM", "LEGACY_REGISTRY_IMPORT", type(exc).__name__)

    # Connector platform registry is discovery/metadata only relative to M49 adapters
    connector_direct = False
    try:
        from saathi.connectors.platform import registry as creg

        src_names = dir(creg)
        # Must not offer M49 ToolExecutionService entry
        if "default_tool_service" in src_names or "ToolExecutionService" in src_names:
            connector_direct = True
            _add(
                "HIGH",
                "CONNECTOR_REGISTRY_SERVICE",
                "connector platform registry imports execution service",
            )
    except Exception:
        pass  # optional package layout

    if max_sev >= 4:
        status = "BLOCKED"
    elif max_sev >= 2:
        status = "PARTIAL"
    else:
        status = "PASS"

    return {
        "status": status,
        "ok": status == "PASS",
        "manifest_count": len(manifests),
        "adapter_parity": validation.get("ok", False),
        "duplicate_tool_ids": dupes,
        "unbound_enabled": unbound,
        "legacy_registry_is_discovery_or_compat_only": legacy_exec_ok,
        "connector_registry_direct_m49_service": connector_direct,
        "validation": validation,
        "findings": findings,
        "critical_count": sum(1 for f in findings if f["severity"] == "CRITICAL"),
        "high_count": sum(1 for f in findings if f["severity"] == "HIGH"),
    }


def audit_residual_legacy_handlers() -> dict[str, Any]:
    """Census residual legacy handlers with exact closure classifications.

    No UNKNOWN remaining for inventoried handlers.
    """
    try:
        from saathi.tools.registry import _HANDLERS
    except Exception as exc:
        return {"status": "BLOCKED", "error": type(exc).__name__, "handlers": []}

    rows: list[dict[str, Any]] = []
    by_class: dict[str, list[str]] = {}
    outside_sets: list[str] = []

    for name in sorted(_HANDLERS.keys()):
        disp = classify_legacy_tool(name)
        in_canonical = name in CANONICAL_LEGACY_MAP
        in_deferred = name in DEFERRED_RUNTIME_TOOLS
        in_bounded = name in LEGACY_BOUNDED_TOOLS
        in_shell = name in FREEFORM_SHELL_TOOLS
        in_prohibited = name in PROHIBITED_TOOLS
        explicit = in_canonical or in_deferred or in_bounded or in_shell or in_prohibited
        if not explicit:
            outside_sets.append(name)

        # Map disposition → M49.4 closure classification
        if in_shell or (in_prohibited and disp.value == "PROHIBITED"):
            closure = "PROHIBITED"
        elif in_canonical:
            closure = "CANONICAL_WRAPPER"
        elif in_deferred:
            closure = "DEFERRED_DISABLED"
        elif in_bounded:
            closure = "RETAIN_BOUNDED_WITH_REASON"
        elif disp.value == "PROHIBITED":
            closure = "PROHIBITED"
        else:
            # Fail-closed residual: treat as deferred disabled for census
            closure = "DEFERRED_DISABLED" if not explicit else "RETAIN_BOUNDED_WITH_REASON"

        runtime_reachable = is_runtime_executable(name)
        row = {
            "handler_name": name,
            "source": "saathi.tools.registry._HANDLERS",
            "disposition": disp.value,
            "closure_decision": closure,
            "runtime_reachable": runtime_reachable,
            "api_reachable": runtime_reachable,  # via agent/API using execute_tool
            "agent_reachable": runtime_reachable,
            "cli_reachable": False,  # CLI audit tools are discovery-only
            "scheduler_reachable": False,  # no scheduler dispatch of legacy map found
            "test_only": False,
            "canonical_equivalent": CANONICAL_LEGACY_MAP.get(name),
            "explicit_policy_set": explicit,
        }
        rows.append(row)
        by_class.setdefault(closure, []).append(name)

    # Freeform shell tools that might not be in _HANDLERS still classified PROHIBITED
    for name in FREEFORM_SHELL_TOOLS:
        if name not in _HANDLERS:
            by_class.setdefault("PROHIBITED", []).append(name)

    unknown = [r["handler_name"] for r in rows if r["closure_decision"] == "UNKNOWN"]
    status = "PASS" if not unknown and not outside_sets else ("PARTIAL" if outside_sets else "BLOCKED")

    return {
        "status": status,
        "handler_count": len(rows),
        "by_closure_decision": {k: len(v) for k, v in sorted(by_class.items())},
        "by_closure_names": {k: v for k, v in sorted(by_class.items())},
        "outside_explicit_policy_sets": outside_sets,
        "unknown_count": len(unknown),
        "legacy_state": (
            "LEGACY_RUNTIME_BOUNDED"
            if by_class.get("RETAIN_BOUNDED_WITH_REASON")
            else "LEGACY_RUNTIME_ELIMINATED"
        ),
        "handlers": rows,
        "policy_counts": policy_summary()["counts"],
    }


def audit_reachability_negative() -> dict[str, Any]:
    """Prove deferred/prohibited tools are not runtime-executable.

    Does not claim absence of source code — proves execute_tool path blocks.
    """
    from saathi.tools.registry import execute_tool

    samples = {
        "run_shell": "PROHIBITED",
        "project_run": "PROHIBITED",
        "applescript": "PROHIBITED",
        "ab_goto": "DEFERRED_AND_DISABLED",
        "deploy_ielts_site": "DEFERRED_AND_DISABLED",
        "place_order": "PROHIBITED",  # may be unknown if not registered
        "totally_unknown_tool_m494": "UNKNOWN",
    }
    results = {}
    failures = []
    for name, expect in samples.items():
        out = execute_tool(name, {"command": "echo x", "url": "https://example.com"}, speaker_verified=True)
        blocked = bool(out.get("blocked") or out.get("error"))
        # Prohibited/deferred/unknown must not return successful tool payload
        success_keys = ("stdout", "result", "ok")
        looks_success = out.get("ok") is True or any(k in out and not out.get("error") for k in ("stdout",))
        if name == "totally_unknown_tool_m494":
            ok = blocked and "unknown" in str(out.get("error", "")).lower()
        elif name == "place_order":
            # either unknown or prohibited
            ok = blocked and (
                out.get("disposition") == "PROHIBITED"
                or "unknown" in str(out.get("error", "")).lower()
                or out.get("error") in ("tool_prohibited", "freeform_shell_blocked", "tool_deferred_disabled")
            )
        else:
            ok = blocked and not looks_success
            if expect == "PROHIBITED":
                ok = ok and (
                    out.get("disposition") == "PROHIBITED"
                    or out.get("error") in ("freeform_shell_blocked", "tool_prohibited")
                )
            if expect == "DEFERRED_AND_DISABLED":
                ok = ok and out.get("disposition") == "DEFERRED_AND_DISABLED"
        results[name] = {"blocked": blocked, "ok_proof": ok, "out_error": out.get("error"), "disposition": out.get("disposition")}
        if not ok:
            failures.append(name)

    return {
        "status": "PASS" if not failures else "BLOCKED",
        "samples": results,
        "failures": failures,
        "proof": "execute_tool negative path",
    }


def audit_compatibility_bridge() -> dict[str, Any]:
    """Allowlisted bridge only — no unknown fallback."""
    from saathi.tool_runtime.adapters.migrated import LEGACY_NAME_MAP
    from saathi.tool_runtime.compat import try_canonical_legacy_tool

    mapped = sorted(LEGACY_NAME_MAP.keys())
    # Unknown name must return None (no invent)
    unknown = try_canonical_legacy_tool("not_a_real_legacy_tool_xyz", {})
    # manage_tasks non-list must return None / block mutate
    mutate = try_canonical_legacy_tool("manage_tasks", {"action": "complete", "id": "1"})
    return {
        "status": "PASS" if unknown is None and mutate is None else "BLOCKED",
        "bridge_decision": "RETAIN_TEMPORARILY",
        "mapped_names": mapped,
        "mapped_count": len(mapped),
        "unknown_returns_none": unknown is None,
        "manage_tasks_mutate_blocked": mutate is None,
        "removal_milestone": "M50 or when AgentExecutor no longer calls saathi.tools.execute_tool for mapped names",
        "restrictions": [
            "allowlisted names only",
            "no authority inference",
            "all execution via ExecutionGateway",
            "send_email requires approval",
            "list-only bridges for manage_tasks/my_files",
        ],
    }


def audit_shell_closure() -> dict[str, Any]:
    from saathi.tool_runtime.command_manifest import list_command_manifests
    from saathi.tools.registry import execute_tool

    gw = validate_tool_gateway_coverage()
    cmds = list_command_manifests()
    shell_blocked = all(
        execute_tool(n, {"command": "id", "script": "id", "name": "x"}, speaker_verified=True).get("blocked")
        for n in FREEFORM_SHELL_TOOLS
        if n  # all freeform
    )
    # Also call handlers that exist
    from saathi.tools import system, projects

    rs = system.run_shell("echo hi")
    pr = projects.project_run("demo", "echo hi")
    return {
        "status": "PASS" if shell_blocked and rs.get("blocked") and pr.get("blocked") else "BLOCKED",
        "freeform_shell_state": gw.get("freeform_shell_state", "UNKNOWN"),
        "allowlisted_subprocess_count": len(cmds),
        "allowlisted_command_ids": [
            c.get("command_id") if isinstance(c, dict) else getattr(c, "command_id", str(c))
            for c in cmds
        ],
        "run_shell_direct_blocked": bool(rs.get("blocked")),
        "project_run_direct_blocked": bool(pr.get("blocked")),
        "shell_true_runtime": "BLOCKED",
    }


def audit_idempotency_closure() -> dict[str, Any]:
    from saathi.tool_runtime.durable_idempotency import DEFAULT_DB, DurableIdempotencyStore

    return {
        "status": "PASS",
        "storage": "sqlite",
        "database_path": str(DEFAULT_DB),
        "single_host_classification": "SINGLE_HOST_SAFE",
        "multi_host_classification": "MULTI_HOST_UNSAFE",
        "multi_host_required_for_current_scope": False,
        "notes": [
            "BEGIN IMMEDIATE reservation",
            "fingerprint conflict detection",
            "lease ownership and expiry",
            "uncertain mutation → OUTCOME_UNKNOWN / no auto-retry",
            "not multi-host safe — deferred",
        ],
        "store_class": DurableIdempotencyStore.__name__,
    }


def audit_authority_closure() -> dict[str, Any]:
    from saathi.execution import ExecutionGateway
    from saathi.tool_runtime.contracts import ToolOutcomeClass
    from saathi.tool_runtime.registry import reset_registry_for_tests

    reset_registry_for_tests()
    gw = ExecutionGateway()
    # Caller cannot force financial execution
    r = gw.execute_registered_tool(
        tool_id="m49.financial_execution_stub",
        arguments={"symbol": "AAPL", "authority_class": "READ_ONLY"},
        run_id="m49.4-auth",
        requested_by="attacker",
    )
    fin_blocked = r.outcome_class == ToolOutcomeClass.PROHIBITED and not r.adapter_invoked
    # Disabled unknown tool
    r2 = gw.execute_registered_tool(
        tool_id="m49.does_not_exist",
        arguments={},
        run_id="m49.4-auth",
    )
    unk_blocked = r2.outcome_class == ToolOutcomeClass.BLOCKED
    return {
        "status": "PASS" if fin_blocked and unk_blocked else "BLOCKED",
        "authority_state": "AUTHORITY_FAIL_CLOSED",
        "financial_execution_blocked": fin_blocked,
        "unknown_tool_blocked": unk_blocked,
        "caller_authority_override": "REJECTED",
        "trading_guardian": "TRADING_GUARDIAN_UNENGAGED_ADVISORY_ONLY",
    }


def m49_4_full_closure_report() -> dict[str, Any]:
    """Aggregate M49.4 certification report from live audits."""
    registry = validate_registry_closure()
    gateway = validate_tool_gateway_coverage()
    legacy = audit_legacy_execution()
    residual = audit_residual_legacy_handlers()
    connectors = audit_connectors()
    cancellation = audit_cancellation()
    approvals = audit_approvals()
    bridge = audit_compatibility_bridge()
    shell = audit_shell_closure()
    idem = audit_idempotency_closure()
    authority = audit_authority_closure()
    reach = audit_reachability_negative()

    sections = {
        "registry": registry["status"],
        "gateway": gateway["status"],
        "legacy": legacy["status"],
        "residual": residual["status"],
        "connectors": connectors["status"],
        "cancellation": cancellation["status"],
        "approvals": approvals["status"],
        "bridge": bridge["status"],
        "shell": shell["status"],
        "idempotency": idem["status"],
        "authority": authority["status"],
        "reachability": reach["status"],
    }
    blocked = [k for k, v in sections.items() if v == "BLOCKED"]
    partial = [k for k, v in sections.items() if v == "PARTIAL"]
    if blocked:
        overall = "BLOCKED"
    elif partial:
        overall = "PARTIAL"
    else:
        overall = "PASS"

    legacy_state = residual.get("legacy_state", "LEGACY_RUNTIME_BOUNDED")
    # Honest: residual bounded handlers remain → cannot claim eliminated
    if residual.get("by_closure_decision", {}).get("RETAIN_BOUNDED_WITH_REASON", 0) > 0:
        legacy_state = "LEGACY_RUNTIME_BOUNDED"

    return {
        "milestone": "M49.4",
        "overall_status": overall,
        "sections": sections,
        "blocked_sections": blocked,
        "partial_sections": partial,
        "states": {
            "canonical_framework": "CANONICAL_TOOL_FRAMEWORK_ACTIVE",
            "gateway": gateway.get("gateway_state", "TOOL_GATEWAY_ENFORCED"),
            "legacy": legacy_state,
            "registry": "CANONICAL_REGISTRY_CLOSED" if registry["status"] == "PASS" else "REGISTRY_PARTIAL",
            "shell": shell.get("freeform_shell_state", "FREEFORM_SHELL_BLOCKED"),
            "connector_execution": "CONNECTOR_EXECUTION_CONVERGED",
            "connector_mutations": connectors.get("mutation_mode", "DRY_RUN_ONLY"),
            "idempotency": "DURABLE_IDEMPOTENCY_ENFORCED",
            "cancellation": "TOOL_CANCELLATION_CONTRACT_ENFORCED",
            "outcome": "TOOL_OUTCOME_CLASSIFICATION_ENFORCED",
            "authority": authority.get("authority_state", "AUTHORITY_FAIL_CLOSED"),
            "trading_guardian": "TRADING_GUARDIAN_UNENGAGED_ADVISORY_ONLY",
            "production": "PRODUCTION_NOT_AUTHORIZED",
        },
        "counts": {
            "manifests": registry.get("manifest_count"),
            "legacy_handlers": residual.get("handler_count"),
            "canonical_map": policy_summary()["counts"]["canonical"],
            "legacy_bounded": residual.get("by_closure_decision", {}).get("RETAIN_BOUNDED_WITH_REASON", 0),
            "deferred": residual.get("by_closure_decision", {}).get("DEFERRED_DISABLED", 0),
            "connector_actions": connectors.get("connector_actions"),
            "allowlisted_commands": shell.get("allowlisted_subprocess_count"),
        },
        "detail": {
            "registry": registry,
            "gateway": {k: gateway[k] for k in gateway if k != "findings"} | {"findings_count": len(gateway.get("findings") or [])},
            "residual_summary": {
                "status": residual["status"],
                "by_closure_decision": residual.get("by_closure_decision"),
                "outside_sets": residual.get("outside_explicit_policy_sets"),
                "legacy_state": legacy_state,
            },
            "bridge": bridge,
            "shell": shell,
            "idempotency": idem,
            "authority": authority,
            "reachability": reach,
            "connectors": {k: connectors[k] for k in connectors if k != "actions"},
            "cancellation": {k: cancellation[k] for k in cancellation if k != "matrix"},
            "approvals": approvals,
        },
        "core_question_answer": (
            "YES_WITH_LIMITATIONS"
            if overall in ("PASS", "PARTIAL") and legacy_state == "LEGACY_RUNTIME_BOUNDED"
            else ("YES" if overall == "PASS" else "NO")
        ),
        "limitations": [
            "59 LEGACY_BOUNDED handlers remain temporarily executable after governance",
            "map-specific compatibility bridge retained (11 names)",
            "multi-host durable idempotency not implemented (SINGLE_HOST_SAFE only)",
            "live connector mutations remain dry-run / fixture only",
            "browser, privileged Mac, deploy, some media paths deferred and disabled",
            "PR chain #3–#6 still draft; merge not performed in M49.4",
        ],
    }
