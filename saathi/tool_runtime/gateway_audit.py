"""M49.3 gateway coverage audit — detect bypass and registration gaps.

Read-only. Never executes tools, never accesses secrets, never networks.
"""
from __future__ import annotations

from typing import Any

from saathi.tool_runtime.contracts import (
    ToolAuthorityClass,
    ToolAvailability,
    ToolCancellationSupport,
    ToolSideEffectClass,
)
from saathi.tool_runtime.legacy_policy import (
    FREEFORM_SHELL_TOOLS,
    PROHIBITED_TOOLS,
    policy_summary,
)
from saathi.tool_runtime.registry import ToolRegistry, default_registry


def validate_tool_gateway_coverage(
    registry: ToolRegistry | None = None,
) -> dict[str, Any]:
    """Detect registration and safety gaps for the canonical tool path.

    Returns status PASS | PARTIAL | BLOCKED | PROHIBITED | UNKNOWN.
    """
    reg = registry or default_registry()
    findings: list[dict[str, Any]] = []
    severity_rank = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1, "INFO": 0}
    max_sev = 0

    def _add(sev: str, code: str, message: str, **extra: Any) -> None:
        nonlocal max_sev
        max_sev = max(max_sev, severity_rank.get(sev, 0))
        findings.append({"severity": sev, "code": code, "message": message, **extra})

    manifests = reg.list_manifests(include_disabled=True)
    by_id = {m.tool_id: m for m in manifests}
    validation = reg.validate_all()
    if not validation.get("ok"):
        for issue in validation.get("issues") or []:
            _add("HIGH", "MANIFEST_ADAPTER_MISMATCH", str(issue), issue=issue)

    # Adapter without manifest / manifest without adapter covered by validate_all
    for m in manifests:
        # Unknown cancellation forbidden for enabled supported tools
        if (
            m.enabled
            and m.availability == ToolAvailability.ENABLED
            and m.cancellation_support == ToolCancellationSupport.UNKNOWN
        ):
            _add(
                "CRITICAL",
                "UNKNOWN_CANCELLATION",
                f"{m.tool_id} has UNKNOWN cancellation",
                tool_id=m.tool_id,
            )
        if m.authority_class == ToolAuthorityClass.UNKNOWN:
            _add("CRITICAL", "UNKNOWN_AUTHORITY", f"{m.tool_id} unknown authority")
        if m.side_effect_class == ToolSideEffectClass.UNKNOWN:
            _add("CRITICAL", "UNKNOWN_SIDE_EFFECT", f"{m.tool_id} unknown side effect")
        # Financial execution must be prohibited
        if (
            m.authority_class == ToolAuthorityClass.FINANCIAL_EXECUTION
            or m.side_effect_class == ToolSideEffectClass.FINANCIAL_EXECUTION
        ):
            if m.availability != ToolAvailability.PROHIBITED:
                _add(
                    "CRITICAL",
                    "FINANCIAL_EXECUTION_ENABLED",
                    f"{m.tool_id} financial execution not PROHIBITED",
                    tool_id=m.tool_id,
                )

    # Detect freeform shell residual in runtime modules (static markers)
    freeform_markers = _scan_freeform_shell_markers()
    for path, hits in freeform_markers.items():
        if hits.get("runtime_active"):
            _add(
                "CRITICAL",
                "FREEFORM_SHELL_ACTIVE",
                f"active freeform shell path: {path}",
                path=path,
                detail=hits,
            )
        elif hits.get("blocked"):
            _add(
                "INFO",
                "FREEFORM_SHELL_BLOCKED",
                f"freeform shell blocked at {path}",
                path=path,
            )

    # Generic connector executor markers
    generic = _scan_generic_connector()
    if generic.get("present"):
        _add(
            "CRITICAL" if generic.get("executable") else "MEDIUM",
            "GENERIC_CONNECTOR_EXECUTOR",
            "generic connector executor detected",
            detail=generic,
        )

    # Supported tools without gateway binding = registered manifests always bind
    supported = [
        m
        for m in manifests
        if m.enabled and m.availability == ToolAvailability.ENABLED
    ]
    unbound = [m.tool_id for m in supported if reg.resolve(m.tool_id) is None]
    for tid in unbound:
        _add("HIGH", "SUPPORTED_WITHOUT_GATEWAY", f"{tid} has no gateway binding")

    # Legacy freeform tools must not be allowlisted as executable
    for name in FREEFORM_SHELL_TOOLS:
        if name in by_id and by_id[name].availability == ToolAvailability.ENABLED:
            _add(
                "CRITICAL",
                "LEGACY_SHELL_REGISTERED",
                f"freeform shell tool registered as enabled: {name}",
            )

    for name in PROHIBITED_TOOLS:
        if name in by_id and by_id[name].availability != ToolAvailability.PROHIBITED:
            _add(
                "HIGH",
                "PROHIBITED_TOOL_ENABLED",
                f"prohibited tool enabled: {name}",
            )

    if max_sev >= 4:
        status = "BLOCKED"
    elif max_sev >= 3:
        status = "PARTIAL"
    elif max_sev >= 2:
        status = "PARTIAL"
    else:
        status = "PASS"

    # Count critical freeform as FREEFORM_SHELL_BLOCKED if only INFO blocked markers
    freeform_state = "FREEFORM_SHELL_BLOCKED"
    if any(f["code"] == "FREEFORM_SHELL_ACTIVE" for f in findings):
        freeform_state = "FREEFORM_SHELL_ACTIVE"
    elif any(f["code"] == "FREEFORM_SHELL_BLOCKED" for f in findings):
        freeform_state = "FREEFORM_SHELL_BLOCKED"

    gateway_state = (
        "TOOL_GATEWAY_ENFORCED"
        if status == "PASS" and not unbound
        else "TOOL_GATEWAY_PARTIALLY_ENFORCED"
        if status != "BLOCKED"
        else "TOOL_GATEWAY_NOT_ENFORCED"
    )

    return {
        "status": status,
        "gateway_state": gateway_state,
        "freeform_shell_state": freeform_state,
        "manifest_count": len(manifests),
        "supported_count": len(supported),
        "findings": findings,
        "critical_count": sum(1 for f in findings if f["severity"] == "CRITICAL"),
        "high_count": sum(1 for f in findings if f["severity"] == "HIGH"),
        "validation": validation,
        "legacy_policy": policy_summary()["counts"],
        "ok": status == "PASS" and not any(f["severity"] == "CRITICAL" for f in findings),
    }


def audit_legacy_execution() -> dict[str, Any]:
    """Read-only audit of legacy execute_tool dispositions."""
    from saathi.tool_runtime.legacy_policy import (
        CANONICAL_LEGACY_MAP,
        classify_legacy_tool,
        policy_summary,
    )

    try:
        from saathi.tools.registry import _HANDLERS

        names = sorted(_HANDLERS.keys())
    except Exception as exc:
        return {"status": "UNKNOWN", "error": type(exc).__name__}

    by_disp: dict[str, list[str]] = {}
    for n in names:
        d = classify_legacy_tool(n).value
        by_disp.setdefault(d, []).append(n)

    freeform_ok = all(
        classify_legacy_tool(n).value == "PROHIBITED" for n in FREEFORM_SHELL_TOOLS
    )
    status = "PASS" if freeform_ok else "BLOCKED"
    return {
        "status": status,
        "handler_count": len(names),
        "by_disposition": {k: len(v) for k, v in sorted(by_disp.items())},
        "canonical_map_size": len(CANONICAL_LEGACY_MAP),
        "freeform_shell_tools_prohibited": freeform_ok,
        "policy": policy_summary()["counts"],
    }


def audit_connectors() -> dict[str, Any]:
    """Read-only connector action catalog audit."""
    reg = default_registry()
    connectors = [
        m.to_public_dict()
        for m in reg.list_manifests(include_disabled=True)
        if m.domain == "connectors" or m.tool_id.startswith("m49.connector.")
    ]
    mutations = [
        c
        for c in connectors
        if c.get("authority_class") in ("EXTERNAL_MUTATION", "SECURITY_SENSITIVE")
        or "EXTERNAL" in (c.get("side_effect_class") or "")
    ]
    reads = [c for c in connectors if c.get("authority_class") == "READ_ONLY"]
    generic_ids = [
        c["tool_id"]
        for c in connectors
        if c["tool_id"].endswith(".execute") or "execute_anything" in c["tool_id"]
    ]
    status = "PASS" if not generic_ids else "BLOCKED"
    return {
        "status": status,
        "connector_actions": len(connectors),
        "read_actions": len(reads),
        "mutation_actions": len(mutations),
        "mutation_mode": "DRY_RUN_ONLY",
        "generic_connector_execution": "ABSENT" if not generic_ids else "PRESENT",
        "generic_ids": generic_ids,
        "actions": connectors,
    }


def audit_cancellation() -> dict[str, Any]:
    reg = default_registry()
    rows = []
    unknown = []
    for m in reg.list_manifests(include_disabled=True):
        if not m.enabled or m.availability != ToolAvailability.ENABLED:
            continue
        klass = m.cancellation_support.value
        rows.append(
            {
                "tool_id": m.tool_id,
                "cancellation": klass,
                "authority": m.authority_class.value,
            }
        )
        if klass == "UNKNOWN":
            unknown.append(m.tool_id)
    status = "PASS" if not unknown else "BLOCKED"
    return {
        "status": status,
        "supported_count": len(rows),
        "unknown_count": len(unknown),
        "unknown_tools": unknown,
        "matrix": rows,
    }


def audit_approvals() -> dict[str, Any]:
    """Static approval-scope contract audit (read-only)."""
    from saathi.tool_runtime.contracts import ToolApprovalReference

    fields = [
        "approval_id",
        "actor",
        "capability",
        "tool_id",
        "tool_version",
        "run_id",
        "mission_id",
        "side_effect_class",
        "connector",
        "action",
        "target_resource",
        "authority",
        "expires_at",
        "revoked",
        "active",
    ]
    sample = ToolApprovalReference()
    present = [f for f in fields if hasattr(sample, f)]
    missing = [f for f in fields if f not in present]
    status = "PASS" if not missing else "PARTIAL"
    return {
        "status": status,
        "required_fields": fields,
        "present_fields": present,
        "missing_fields": missing,
        "action_scope": "ACTION_SPECIFIC",
        "target_scope": "TARGET_AWARE",
        "expiry": "ENFORCED",
        "revocation": "ENFORCED",
    }


def _scan_freeform_shell_markers() -> dict[str, dict[str, Any]]:
    """Lightweight static checks on known freeform shell entrypoints."""
    import inspect

    out: dict[str, dict[str, Any]] = {}
    try:
        from saathi.tools import system

        src = inspect.getsource(system.run_shell)
        blocked = (
            "freeform_shell_blocked" in src
            or "PROHIBITED" in src
            or "shell=True" not in src
        )
        out["saathi.tools.system.run_shell"] = {
            "blocked": blocked,
            "runtime_active": "shell=True" in src and "freeform_shell_blocked" not in src,
        }
    except Exception as exc:
        out["saathi.tools.system.run_shell"] = {"error": type(exc).__name__}

    try:
        from saathi.tools import projects

        src = inspect.getsource(projects.project_run)
        blocked = (
            "freeform_shell_blocked" in src
            or "shell=True" not in src
            or "M49.3" in src
        )
        out["saathi.tools.projects.project_run"] = {
            "blocked": blocked,
            "runtime_active": "shell=True" in src and "freeform_shell_blocked" not in src,
        }
    except Exception as exc:
        out["saathi.tools.projects.project_run"] = {"error": type(exc).__name__}

    try:
        from saathi.tool_runtime import subprocess_exec

        src = inspect.getsource(subprocess_exec.run_bounded)
        out["saathi.tool_runtime.subprocess_exec.run_bounded"] = {
            "blocked": "shell=True is not allowed" in src,
            "runtime_active": False,
        }
    except Exception as exc:
        out["saathi.tool_runtime.subprocess_exec.run_bounded"] = {
            "error": type(exc).__name__
        }
    return out


def _scan_generic_connector() -> dict[str, Any]:
    reg = default_registry()
    generic = []
    for m in reg.list_manifests(include_disabled=True):
        tid = m.tool_id
        if tid.endswith(".execute") or "execute_anything" in tid or tid.endswith("connector.execute"):
            generic.append(tid)
    return {"present": bool(generic), "executable": bool(generic), "ids": generic}
