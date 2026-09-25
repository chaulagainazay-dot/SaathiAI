"""M333 operational diagnostics centre.

One entry point verifies every subsystem the mission names and folds the results into
a single unified report. Diagnostics observe and report; they never repair, activate,
or escalate anything.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TYPE_CHECKING

from saathi.platform.tg.production_readiness.models import (
    BOUNDARY_VALUES,
    SCHEMA_VERSION,
    DiagnosticResult,
    DiagnosticStatus,
    digest,
)

if TYPE_CHECKING:
    from saathi.platform.tg.production_readiness.service import OperationsService

SUBSYSTEMS = (
    "provider_contracts",
    "replay_engine",
    "authority_system",
    "approval_engine",
    "storage",
    "configuration",
    "browser_certification_history",
)

BROWSER_CERT_PATHS = (
    "docs/trading/m320_m327_evidence/browser/M327_BROWSER_CERT.json",
    "docs/trading/m312_m319_evidence/browser/M319_BROWSER_CERT.json",
)


def _provider_contracts_check(service: "OperationsService") -> DiagnosticResult:
    contracts = service.provider_contracts
    providers = contracts.list_providers()
    security = contracts.security_scan()
    ok = (
        providers["count"] >= 2
        and providers["any_real"] is False
        and providers["any_connected"] is False
        and providers["any_authenticated"] is False
        and security["ok"] is True
    )
    return DiagnosticResult(
        check_id="diag.provider_contracts",
        subsystem="provider_contracts",
        status=DiagnosticStatus.PASS if ok else DiagnosticStatus.FAIL,
        summary="Provider contracts remain credentialless and offline"
        if ok else "Provider contract boundary check failed",
        detail={
            "provider_count": providers["count"],
            "any_real": providers["any_real"],
            "any_connected": providers["any_connected"],
            "any_authenticated": providers["any_authenticated"],
            "security_ok": security["ok"],
            "security_findings": security["findings"],
        },
    )


def _replay_engine_check(service: "OperationsService") -> DiagnosticResult:
    contracts = service.provider_contracts
    fixtures = contracts.replay_fixtures()
    payload = {
        "provider_id": "saathi.replay.market.v1",
        "operation": "quotes.get",
        "params": {"symbol": "AAPL"},
        "idempotency_key": "diag:replay:quote:AAPL:v1",
    }
    first = contracts.request(payload)
    second = contracts.request(payload)
    deterministic = first == second
    ok = fixtures["count"] > 0 and fixtures["deterministic"] is True and deterministic
    return DiagnosticResult(
        check_id="diag.replay_engine",
        subsystem="replay_engine",
        status=DiagnosticStatus.PASS if ok else DiagnosticStatus.FAIL,
        summary="Replay engine is deterministic and fixture-bound"
        if ok else "Replay engine determinism check failed",
        detail={
            "fixture_count": fixtures["count"],
            "recorded_offline": fixtures["recorded_offline"],
            "network_capture": fixtures["network_capture"],
            "repeat_dispatch_identical": deterministic,
        },
    )


def _authority_system_check(service: "OperationsService") -> DiagnosticResult:
    from saathi.platform.tg.connectivity_governance.authority import (
        prove_deny_overrides_allow,
        prove_emergency_override,
        prove_expiry,
        prove_no_implicit_expansion,
        prove_revocation,
    )

    proofs = {
        "no_implicit_expansion": prove_no_implicit_expansion()["ok"],
        "deny_overrides_allow": prove_deny_overrides_allow()["ok"],
        "expiry": prove_expiry()["ok"],
        "revocation": prove_revocation()["ok"],
        "emergency_override": prove_emergency_override()["ok"],
        "milestone_locks_false": service.authority_locks_ok(),
    }
    ok = all(proofs.values())
    return DiagnosticResult(
        check_id="diag.authority_system",
        subsystem="authority_system",
        status=DiagnosticStatus.PASS if ok else DiagnosticStatus.FAIL,
        summary="Authority lattice proofs hold and every hard lock is false"
        if ok else "Authority system proof failed",
        detail=proofs,
    )


def _approval_engine_check(service: "OperationsService") -> DiagnosticResult:
    approvals = service.governance.approvals.list_approvals()
    ok = approvals["any_active_connectivity"] is False
    return DiagnosticResult(
        check_id="diag.approval_engine",
        subsystem="approval_engine",
        status=DiagnosticStatus.PASS if ok else DiagnosticStatus.FAIL,
        summary="No approval activates connectivity"
        if ok else "An approval reported active connectivity",
        detail={
            "approval_count": approvals.get("count", 0),
            "any_active_connectivity": approvals["any_active_connectivity"],
            "approval_equals_activation": False,
        },
    )


def _storage_check(service: "OperationsService") -> DiagnosticResult:
    schema = service.governance.store.schema_scan()
    backups = service.backups.verify_all()
    ok = schema["ok"] and backups["ok"]
    return DiagnosticResult(
        check_id="diag.storage",
        subsystem="storage",
        status=DiagnosticStatus.PASS if ok else DiagnosticStatus.FAIL,
        summary="Storage schema is credential-free and snapshots verify"
        if ok else "Storage diagnostic failed",
        detail={
            "schema_ok": schema["ok"],
            "table_count": len(schema["tables"]),
            "forbidden_fields_found": schema["forbidden_fields_found"],
            "snapshots_verified": backups["verified_count"],
            "snapshot_failures": backups["failures"],
        },
    )


def _configuration_check(service: "OperationsService") -> DiagnosticResult:
    config = service.configuration_snapshot_payload()
    boundary_ok = all(
        config["authority_locks"][key] is False for key in config["authority_locks"]
    )
    ok = boundary_ok and config["offline_only"] is True
    return DiagnosticResult(
        check_id="diag.configuration",
        subsystem="configuration",
        status=DiagnosticStatus.PASS if ok else DiagnosticStatus.FAIL,
        summary="Configuration is offline and every authority lock is false"
        if ok else "Configuration diagnostic failed",
        detail={
            "schema_version": config["schema_version"],
            "authority_lock_count": len(config["authority_locks"]),
            "all_locks_false": boundary_ok,
            "offline_only": config["offline_only"],
            "config_digest": digest(config),
        },
    )


def _browser_history_check(service: "OperationsService") -> DiagnosticResult:
    entries: list[dict[str, Any]] = []
    missing: list[str] = []
    for relative in BROWSER_CERT_PATHS:
        path = Path(service.repo_root) / relative
        if not path.exists():
            missing.append(relative)
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            missing.append(relative)
            continue
        entries.append({
            "path": relative,
            "verdict": payload.get("verdict") or payload.get("browser_verdict"),
            "ok": payload.get("ok"),
            "milestone": payload.get("milestone") or payload.get("milestones"),
        })
    if entries and not missing:
        status = DiagnosticStatus.PASS
    elif entries:
        status = DiagnosticStatus.WARN
    else:
        status = DiagnosticStatus.SKIPPED
    return DiagnosticResult(
        check_id="diag.browser_certification_history",
        subsystem="browser_certification_history",
        status=status,
        summary=f"{len(entries)} prior browser certification record(s) readable",
        detail={
            "records": entries,
            "missing": missing,
            "history_is_read_only": True,
        },
    )


CHECKS = (
    _provider_contracts_check,
    _replay_engine_check,
    _authority_system_check,
    _approval_engine_check,
    _storage_check,
    _configuration_check,
    _browser_history_check,
)


def run_diagnostics(service: "OperationsService") -> dict[str, Any]:
    """Run every subsystem check and fold them into one unified report."""
    results = [check(service) for check in CHECKS]
    payload = [result.to_dict() for result in results]
    counts = {status.value: 0 for status in DiagnosticStatus}
    for result in results:
        counts[result.status.value] += 1
    failures = [
        result.check_id for result in results if result.status is DiagnosticStatus.FAIL
    ]
    covered = {result.subsystem for result in results}
    missing = [name for name in SUBSYSTEMS if name not in covered]
    report = {
        "ok": not failures and not missing,
        "milestone": "M333",
        "name": "Operational Diagnostics Centre",
        "schema_version": SCHEMA_VERSION,
        "report_id": "",
        "subsystems": list(SUBSYSTEMS),
        "covered_subsystems": sorted(covered),
        "missing_subsystems": missing,
        "coverage_complete": not missing,
        "check_count": len(results),
        "counts": counts,
        "failures": failures,
        "results": payload,
        "generated_at": service.clock.advance(),
        "unified_report": True,
        "auto_remediation": False,
        **BOUNDARY_VALUES,
    }
    report["report_id"] = "diag_" + digest(payload)[:16]
    report["report_digest"] = digest(payload)
    return report
