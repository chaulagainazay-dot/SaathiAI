"""M335 hard-gate certification for production readiness and operational resilience.

Every check is a fail-closed assertion. The terminal verdict is only emitted when all
of them hold; anything else degrades to PRODUCTION_READINESS_NOT_CERTIFIED.
"""
from __future__ import annotations

from typing import Any, TYPE_CHECKING

from saathi.platform.tg.connectivity_governance.authority import (
    prove_deny_overrides_allow,
    prove_no_implicit_expansion,
)
from saathi.platform.tg.connectivity_governance.storage import evidence_hash
from saathi.platform.tg.production_readiness import performance as performance_module
from saathi.platform.tg.production_readiness.alerts import ALLOWED_DESTINATIONS
from saathi.platform.tg.production_readiness.backup import BackupEngine
from saathi.platform.tg.production_readiness.diagnostics import SUBSYSTEMS
from saathi.platform.tg.production_readiness.errors import OperationsError
from saathi.platform.tg.production_readiness.models import (
    AUTHORITY_LOCKS,
    BOUNDARY_VALUES,
    BROWSER_CERT_VERDICT,
    CURRENT_MATURITY,
    FORBIDDEN_ALERT_DESTINATIONS,
    HARD_AUTHORITY_KEYS,
    MAX_STATE,
    NOT_CERTIFIED_VERDICT,
    TERMINAL_STATEMENTS,
    TERMINAL_VERDICT,
    AlertSeverity,
    AlertState,
    BackupKind,
    HealthState,
    MetricKind,
    authority_locks_intact,
)

if TYPE_CHECKING:
    from saathi.platform.tg.production_readiness.service import OperationsService

LIMITATIONS = (
    "Offline operational observation only; no external telemetry or cloud monitoring",
    "Alerts are delivered to the control centre, local logs and audit history only",
    "Recovery is simulated against local snapshots; live state is never mutated",
    "Load validation is a deterministic model, not generated traffic",
    "The operations dashboard is read-only; it exposes no execution or deployment control",
    "No provider connectivity, credential, OAuth, account, order, canary or live-trading path",
)


def certify_production_readiness(service: "OperationsService") -> dict[str, Any]:
    checks: dict[str, bool] = {}
    failures: list[str] = []

    # ── boundary ────────────────────────────────────────────────────────────
    checks["authority_locks_false"] = authority_locks_intact()
    checks["hard_authority_keys_complete"] = set(HARD_AUTHORITY_KEYS) == {
        "REAL_CONNECTIVITY_AUTHORIZED",
        "BROKER_CONNECTIVITY_AUTHORIZED",
        "OAUTH_AUTHORIZED",
        "CREDENTIAL_PROVISIONING_AUTHORIZED",
        "ACCOUNT_ACCESS_AUTHORIZED",
        "BALANCE_READ_AUTHORIZED",
        "POSITION_READ_AUTHORIZED",
        "ORDER_SUBMISSION_AUTHORIZED",
        "ORDER_EXECUTION_AUTHORIZED",
        "CANARY_ACTIVATION_AUTHORIZED",
        "LIVE_TRADING_AUTHORIZED",
    }
    checks["every_hard_lock_is_false"] = all(
        AUTHORITY_LOCKS[key] is False for key in HARD_AUTHORITY_KEYS
    )
    checks["deny_overrides_allow"] = prove_deny_overrides_allow()["ok"] is True
    checks["authority_does_not_expand"] = prove_no_implicit_expansion()["ok"] is True
    checks["approval_does_not_activate_connectivity"] = (
        service.governance.approvals.list_approvals()["any_active_connectivity"] is False
    )

    # ── M328 health ─────────────────────────────────────────────────────────
    health = service.health.snapshot()
    checks["health_states_exact"] = set(health["supported_states"]) == {
        state.value for state in HealthState
    } and len(health["supported_states"]) == 5
    checks["health_domain_coverage"] = health["domain_coverage_complete"] is True
    checks["health_grants_no_authority"] = (
        health["health_grants_authority"] is False
        and health["degradation_triggers_remediation"] is False
    )
    checks["health_rollup_correct"] = service.health.rollup_proof()["ok"] is True

    # Degradation must be observable and must still grant nothing.
    service.health.force_state("platform.scheduler", HealthState.DEGRADED)
    degraded = service.health.snapshot()
    checks["degradation_visible"] = degraded["overall_state"] == HealthState.DEGRADED.value
    checks["degradation_grants_nothing"] = (
        degraded["health_grants_authority"] is False
        and degraded["LIVE_TRADING_AUTHORIZED"] is False
    )
    service.health.force_state("platform.scheduler", None)
    checks["health_state_restored"] = (
        service.health.snapshot()["overall_state"] == health["overall_state"]
    )

    # ── M329 observability ──────────────────────────────────────────────────
    trace = service.observability.start_trace("cert.observability", "certification")
    child = service.observability.start_trace(
        "cert.observability.child", "certification", parent=trace,
    )
    service.observability.log("INFO", "certification trace root", trace=trace)
    service.observability.log("INFO", "certification trace child", trace=child)
    service.observability.log(
        "WARN",
        "certification redaction probe",
        trace=trace,
        fields={"api_key": "should-never-survive", "component": "certification"},
    )
    correlated = service.observability.trace(trace.trace_id)
    checks["trace_correlation"] = (
        correlated["record_count"] >= 3 and correlated["span_count"] >= 2
    )
    checks["trace_parent_child_linked"] = any(
        span["parent_span_id"] == trace.span_id for span in correlated["spans"]
    )
    checks["observability_redaction"] = (
        service.observability.redaction_scan()["ok"] is True
    )
    checks["observability_local_only"] = (
        service.observability.posture()["external_telemetry_providers"] == []
    )
    checks["operation_timelines_present"] = (
        service.observability.timelines()["count"] > 0
    )
    checks["execution_history_has_no_orders"] = (
        service.observability.execution_history()["order_execution_records"] == 0
    )
    audit_view = service.observability.audit_visualization(
        service.governance.store.list_audit(50)
    )
    checks["audit_visualization_available"] = audit_view["ok"] is True

    # ── M330 metrics ────────────────────────────────────────────────────────
    metrics = service.metrics.summary()
    checks["metric_kind_coverage"] = metrics["coverage_complete"] is True and set(
        metrics["covered_kinds"]
    ) >= {kind.value for kind in MetricKind}
    checks["metrics_local_only"] = metrics["cloud_monitoring_exporters"] == []
    checks["metric_thresholds_advisory"] = (
        metrics["thresholds_are_advisory"] is True
        and metrics["autoscaling_triggered"] is False
    )
    first_fingerprint = metrics["fingerprint"]
    checks["metrics_deterministic"] = (
        service.metrics.summary()["fingerprint"] == first_fingerprint
    )

    # ── M331 alerts ─────────────────────────────────────────────────────────
    policy = service.alerts.destination_policy()
    checks["alert_severities_exact"] = set(policy["severities"]) == {
        item.value for item in AlertSeverity
    } and len(policy["severities"]) == 3
    checks["alert_destinations_exact"] = set(policy["allowed_destinations"]) == {
        item.value for item in ALLOWED_DESTINATIONS
    }
    checks["alert_external_destinations_forbidden"] = set(
        policy["forbidden_destinations"]
    ) == set(FORBIDDEN_ALERT_DESTINATIONS)
    checks["alerts_trigger_nothing"] = (
        policy["alerts_trigger_actions"] is False
        and policy["alerts_grant_authority"] is False
    )

    raised = service.alerts.raise_alert(
        AlertSeverity.WARNING,
        "certification.probe",
        "Certification alert lifecycle probe",
        detail={"purpose": "certification"},
    )["alert"]
    acknowledged = service.alerts.acknowledge(raised["alert_id"], "certification")["alert"]
    resolved = service.alerts.resolve(raised["alert_id"], "certification")["alert"]
    checks["alert_lifecycle"] = (
        raised["state"] == AlertState.OPEN.value
        and acknowledged["state"] == AlertState.ACKNOWLEDGED.value
        and resolved["state"] == AlertState.RESOLVED.value
    )
    try:
        service.alerts.acknowledge(raised["alert_id"], "certification")
    except OperationsError as exc:
        checks["resolved_alert_is_terminal"] = (
            exc.code.value == "alert_transition_invalid"
        )
    else:
        checks["resolved_alert_is_terminal"] = False

    try:
        service.alerts.raise_alert(
            AlertSeverity.CRITICAL,
            "certification.probe",
            "Forbidden destination probe",
            destinations=("email",),  # type: ignore[arg-type]
        )
    except OperationsError as exc:
        checks["forbidden_destination_rejected"] = (
            exc.code.value == "forbidden_destination"
        )
    else:
        checks["forbidden_destination_rejected"] = False

    alert_isolation = service.alerts.isolation_scan()
    checks["alert_delivery_local_only"] = (
        alert_isolation["ok"] is True
        and alert_isolation["email_transport_present"] is False
        and alert_isolation["sms_transport_present"] is False
        and alert_isolation["push_transport_present"] is False
    )

    # ── M332 backup and recovery ────────────────────────────────────────────
    snapshots = service.backups.list_snapshots()
    checks["backup_kind_coverage"] = snapshots["coverage_complete"] is True and set(
        snapshots["by_kind"]
    ) == {kind.value for kind in BackupKind}
    checks["backup_local_only"] = (
        snapshots["cloud_targets"] == []
        and snapshots["storage_target"] == "local_offline_store"
    )
    verification = service.verify_backups()
    checks["backup_integrity_verified"] = verification["ok"] is True

    recovery = service.simulate_recovery()
    checks["recovery_simulation_succeeds"] = recovery["ok"] is True
    checks["recovery_does_not_mutate_live_state"] = (
        recovery["recovery"]["live_state_mutated"] is False
        and recovery["recovery"]["applied_to_production"] is False
        and recovery["recovery"]["restored_credentials"] == 0
        and recovery["recovery"]["restored_accounts"] == 0
        and recovery["recovery"]["restored_orders"] == 0
    )

    # Corruption must be detected, not silently recovered. The drill runs against a
    # scratch engine so the live snapshot store is never left in a damaged state.
    drill_engine = BackupEngine(clock=service.clock)
    drill = drill_engine.capture(
        BackupKind.CONFIGURATION,
        "certification_corruption_drill",
        {"probe": "corruption", "value": 1},
    )["snapshot"]
    drill_engine.corrupt_for_drill(drill["snapshot_id"])
    corrupted = drill_engine.simulate_recovery(drill["snapshot_id"])
    checks["integrity_mismatch_detected"] = (
        corrupted["ok"] is False
        and corrupted["recovery"]["outcome"] == "INTEGRITY_MISMATCH"
    )
    checks["live_snapshot_store_undamaged"] = service.backups.verify_all()["ok"] is True

    try:
        drill_engine.capture(
            BackupKind.CONFIGURATION,
            "certification_forbidden_field_probe",
            {"api_key": "nope"},
        )
    except OperationsError as exc:
        checks["forbidden_snapshot_field_rejected"] = exc.code.value == "forbidden_field"
    else:
        checks["forbidden_snapshot_field_rejected"] = False

    # ── M333 diagnostics ────────────────────────────────────────────────────
    diagnostics = service.run_diagnostics()
    checks["diagnostics_subsystem_coverage"] = (
        diagnostics["coverage_complete"] is True
        and set(diagnostics["covered_subsystems"]) == set(SUBSYSTEMS)
    )
    checks["diagnostics_unified_report"] = (
        diagnostics["unified_report"] is True and bool(diagnostics["report_id"])
    )
    checks["diagnostics_no_failures"] = not diagnostics["failures"]
    checks["diagnostics_never_remediate"] = diagnostics["auto_remediation"] is False
    checks["diagnostics_deterministic"] = (
        service.run_diagnostics()["report_digest"] == diagnostics["report_digest"]
    )

    # ── M334 performance ────────────────────────────────────────────────────
    load = service.run_load_validation()
    checks["load_dimension_coverage"] = load["coverage_complete"] is True
    checks["load_within_objectives"] = not load["breaches"]
    checks["load_deterministic_repeatability"] = load["repeatability"]["ok"] is True
    checks["load_is_simulation_only"] = all(
        run["simulation_only"] is True
        and run["network_requests_issued"] == 0
        and run["orders_submitted"] == 0
        for run in load["runs"]
    )
    checks["load_profiles_complete"] = load["profile_count"] == len(
        performance_module.LOAD_PROFILES
    )

    # ── M335 control centre ─────────────────────────────────────────────────
    control = service.control_center()
    checks["control_center_panels_complete"] = set(control["panels"]) == {
        "system_health",
        "metrics",
        "alerts",
        "diagnostics",
        "backups",
        "replay_health",
        "authority_summary",
        "certification_history",
    }
    checks["control_center_read_only"] = (
        control["execution_controls"] == 0
        and control["deployment_controls"] == 0
        and control["mutating_operational_controls"] == 0
        and control["READ_ONLY_OPERATIONS_DASHBOARD"] is True
    )
    checks["control_center_authority_summary"] = (
        control["panels"]["authority_summary"]["all_locks_false"] is True
        and control["panels"]["authority_summary"]["operations_layer_grants_authority"]
        is False
    )
    checks["certification_history_read_only"] = (
        control["panels"]["certification_history"]["read_only"] is True
        and control["panels"]["certification_history"]["history_mutated"] is False
    )
    checks["certification_history_present"] = (
        control["panels"]["certification_history"]["count"] > 0
    )

    # ── composition and isolation ───────────────────────────────────────────
    charter = service.charter()
    checks["no_parallel_monitoring_systems"] = (
        charter["parallel_monitoring_systems_introduced"] == 0
    )
    checks["composes_existing_subsystems"] = set(charter["composed_subsystems"]) >= {
        "governance",
        "authority",
        "approval",
        "certification",
        "replay",
        "provider_contracts",
        "audit",
        "evidence",
        "maturity",
    }
    security = service.security_scan()
    checks["isolation_scan"] = security["isolation"]["ok"] is True
    checks["security_scan"] = security["ok"] is True
    checks["provider_contracts_still_certified"] = (
        service.provider_contracts.security_scan()["ok"] is True
    )
    checks["governance_still_secure"] = security["governance_security_ok"] is True

    maturity = service.maturity()
    checks["maturity_ceiling"] = (
        maturity["current"] == CURRENT_MATURITY
        and maturity["max_state"] == MAX_STATE
        and maturity["can_advance_automatically"] is False
        and maturity["real_connectivity_ready"] is False
        and maturity["production_deployment_ready"] is False
    )

    for name, passed in checks.items():
        if not passed:
            failures.append(name)
    ok = not failures
    verdict = TERMINAL_VERDICT if ok else NOT_CERTIFIED_VERDICT
    result = {
        "ok": ok,
        "verdict": verdict,
        "milestones": "M328-M335",
        "max_state": MAX_STATE,
        "current_maturity": CURRENT_MATURITY,
        "browser_cert_verdict_target": BROWSER_CERT_VERDICT,
        "check_count": len(checks),
        "checks": checks,
        "failures": failures,
        "statements": list(TERMINAL_STATEMENTS),
        "limitations": list(LIMITATIONS),
        "hard_authority_locks": dict(AUTHORITY_LOCKS),
        **BOUNDARY_VALUES,
    }
    result["evidence_hash"] = evidence_hash(result)
    service.governance.store.audit(
        "operations_certify",
        "system",
        "M328-M335",
        {"verdict": verdict, "ok": ok, "evidence_hash": result["evidence_hash"]},
    )
    return result
