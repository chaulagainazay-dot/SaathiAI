"""M328–M335 production readiness, observability and operational resilience tests."""
from __future__ import annotations

import ast
import socket
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from saathi.platform.tg.production_readiness import performance as performance_module
from saathi.platform.tg.production_readiness.alerts import ALLOWED_DESTINATIONS
from saathi.platform.tg.production_readiness.backup import (
    FORBIDDEN_BACKUP_TARGETS,
    BackupEngine,
)
from saathi.platform.tg.production_readiness.diagnostics import SUBSYSTEMS
from saathi.platform.tg.production_readiness.errors import (
    OperationsError,
    OperationsErrorCode,
    error_envelope,
    normalize_error,
)
from saathi.platform.tg.production_readiness.health import (
    REQUIRED_DOMAINS,
    health_to_alert_severity,
)
from saathi.platform.tg.production_readiness.metrics import (
    METRIC_THRESHOLDS,
    MetricsEngine,
    classify,
    percentile,
)
from saathi.platform.tg.production_readiness.models import (
    AUTHORITY_LOCKS,
    BOUNDARY_VALUES,
    BROWSER_CERT_VERDICT,
    CURRENT_MATURITY,
    FORBIDDEN_ALERT_DESTINATIONS,
    FORBIDDEN_OBSERVABILITY_FIELDS,
    HARD_AUTHORITY_KEYS,
    MAX_STATE,
    REDACTION_MARKER,
    SCHEMA_VERSION,
    TERMINAL_VERDICT,
    AlertDestination,
    AlertSeverity,
    AlertState,
    BackupKind,
    DeterministicClock,
    DiagnosticStatus,
    HealthDomain,
    HealthState,
    LogLevel,
    MetricKind,
    authority_locks_intact,
    redact,
    worst_health,
)
from saathi.platform.tg.production_readiness.observability import (
    FORBIDDEN_TELEMETRY_MODULES,
    ObservabilityEngine,
)
from saathi.platform.tg.production_readiness.service import (
    ALLOWED_UI_ACTIONS,
    FORBIDDEN_NETWORK_IMPORTS,
    FORBIDDEN_UI_CONTROLS,
    OperationsService,
    reset_operations_for_tests,
)

PACKAGE_DIR = Path(__file__).resolve().parents[1] / "saathi/platform/tg/production_readiness"
UI_DIR = Path(__file__).resolve().parents[1] / "saathi-os/app/trading/operations"


@pytest.fixture()
def service(tmp_path: Path) -> OperationsService:
    return reset_operations_for_tests(tmp_path / "operations.db")


@pytest.fixture()
def api_client(tmp_path: Path, monkeypatch, service: OperationsService):
    from saathi.platform.service import reset_platform_for_tests
    from saathi.tool_runtime.registry import reset_registry_for_tests

    reset_registry_for_tests()
    platform = reset_platform_for_tests(tmp_path / "platform_api.db")
    import saathi.platform.api as api_module
    import saathi.platform.service as service_module

    monkeypatch.setattr(service_module, "_DEFAULT", platform)
    monkeypatch.setattr(api_module, "default_platform", lambda: platform)
    monkeypatch.setattr(api_module, "_tg_operations", lambda: service)
    from saathi.server import app

    client = TestClient(app)
    bootstrap = client.post(
        "/api/v1/platform/bootstrap",
        json={"email": "m335@local", "name": "M335 Owner"},
    )
    assert bootstrap.status_code == 200
    login = client.post("/api/v1/platform/auth/login", json={"email": "m335@local"})
    assert login.status_code == 200
    return client, {"X-Platform-Token": login.json()["token"]}


# ── hard authority boundary ─────────────────────────────────────────────────


def test_hard_authority_boundary_is_false():
    required = {
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
    assert set(HARD_AUTHORITY_KEYS) == required
    for key in required:
        assert AUTHORITY_LOCKS[key] is False
        assert BOUNDARY_VALUES[key] is False
    assert authority_locks_intact() is True


def test_boundary_values_forbid_production_and_telemetry():
    for key in (
        "PRODUCTION_AUTHORIZED",
        "DEPLOYMENT_AUTHORIZED",
        "EXTERNAL_TELEMETRY_AUTHORIZED",
        "CLOUD_MONITORING_AUTHORIZED",
        "CLOUD_BACKUP_AUTHORIZED",
        "PAPER_EXECUTION_AUTHORIZED",
    ):
        assert BOUNDARY_VALUES[key] is False
    assert BOUNDARY_VALUES["max_state"] == MAX_STATE == "OPERATIONALLY_READY_OFFLINE"
    assert BOUNDARY_VALUES["current_maturity"] == CURRENT_MATURITY


def test_terminal_verdict_matches_mission():
    assert TERMINAL_VERDICT == (
        "PRODUCTION_READINESS_AND_OPERATIONAL_RESILIENCE_CERTIFIED_WITH_LIMITATIONS"
    )
    assert BROWSER_CERT_VERDICT.endswith("BROWSER_CERT_PASSED_WITH_LIMITATIONS")
    assert SCHEMA_VERSION == "m328.production_readiness.v1"


# ── M328 health ─────────────────────────────────────────────────────────────


def test_health_supports_exactly_the_five_required_states():
    assert {state.value for state in HealthState} == {
        "HEALTHY", "WARNING", "DEGRADED", "FAILED", "MAINTENANCE",
    }


def test_health_covers_every_required_domain(service: OperationsService):
    snapshot = service.health.snapshot()
    covered = {domain["domain"] for domain in snapshot["domains"]}
    assert covered == {domain.value for domain in REQUIRED_DOMAINS}
    assert snapshot["domain_coverage_complete"] is True
    assert snapshot["missing_required_domains"] == []


def test_health_rollup_takes_the_worst_child_state():
    assert worst_health([]) is HealthState.HEALTHY
    assert worst_health([HealthState.HEALTHY, HealthState.MAINTENANCE]) is HealthState.MAINTENANCE
    assert worst_health([HealthState.MAINTENANCE, HealthState.WARNING]) is HealthState.WARNING
    assert worst_health([HealthState.WARNING, HealthState.DEGRADED]) is HealthState.DEGRADED
    assert worst_health([HealthState.DEGRADED, HealthState.FAILED]) is HealthState.FAILED
    assert worst_health([HealthState.FAILED, HealthState.HEALTHY]) is HealthState.FAILED


def test_health_rollup_proof_holds(service: OperationsService):
    proof = service.health.rollup_proof()
    assert proof["ok"] is True
    assert all(entry["correct"] for entry in proof["proofs"])


def test_health_baseline_is_healthy(service: OperationsService):
    assert service.health.snapshot()["overall_state"] == "HEALTHY"


def test_degraded_component_never_grants_authority(service: OperationsService):
    service.health.force_state("platform.storage", HealthState.FAILED)
    snapshot = service.health.snapshot()
    assert snapshot["overall_state"] == "FAILED"
    assert snapshot["health_grants_authority"] is False
    assert snapshot["degradation_triggers_remediation"] is False
    assert snapshot["LIVE_TRADING_AUTHORIZED"] is False
    assert snapshot["REAL_CONNECTIVITY_AUTHORIZED"] is False
    service.health.force_state("platform.storage", None)
    assert service.health.snapshot()["overall_state"] == "HEALTHY"


def test_maintenance_state_is_not_an_incident(service: OperationsService):
    service.health.set_maintenance("platform.scheduler", True)
    snapshot = service.health.snapshot()
    assert snapshot["overall_state"] == "MAINTENANCE"
    assert "platform.scheduler" in snapshot["maintenance_components"]
    service.health.set_maintenance("platform.scheduler", False)


def test_probe_exception_reports_failed_not_crash(service: OperationsService):
    def exploding_probe():
        raise RuntimeError("probe fault")

    service.health.register("platform.exploding", HealthDomain.PLATFORM, exploding_probe)
    component = service.health.component("platform.exploding")["component"]
    assert component["state"] == "FAILED"
    assert component["reason"] == "probe_raised"


def test_unknown_health_component_is_rejected(service: OperationsService):
    with pytest.raises(OperationsError) as exc:
        service.health.component("platform.does_not_exist")
    assert exc.value.code is OperationsErrorCode.COMPONENT_UNKNOWN


def test_health_to_alert_severity_mapping():
    assert health_to_alert_severity(HealthState.HEALTHY) is None
    assert health_to_alert_severity(HealthState.MAINTENANCE) == "INFORMATIONAL"
    assert health_to_alert_severity(HealthState.WARNING) == "WARNING"
    assert health_to_alert_severity(HealthState.DEGRADED) == "CRITICAL"
    assert health_to_alert_severity(HealthState.FAILED) == "CRITICAL"


# ── M329 observability ──────────────────────────────────────────────────────


def test_trace_ids_are_deterministic_not_random():
    first = ObservabilityEngine().start_trace("op.alpha", "component.a")
    second = ObservabilityEngine().start_trace("op.alpha", "component.a")
    assert first.trace_id == second.trace_id
    assert first.trace_id.startswith("trace_")


def test_child_span_inherits_trace_and_links_parent():
    engine = ObservabilityEngine()
    root = engine.start_trace("op.root", "component.a")
    child = engine.start_trace("op.child", "component.b", parent=root)
    assert child.trace_id == root.trace_id
    assert child.parent_span_id == root.span_id
    assert child.span_id != root.span_id


def test_correlated_trace_returns_spans_and_records():
    engine = ObservabilityEngine()
    root = engine.start_trace("op.root", "component.a")
    child = engine.start_trace("op.child", "component.b", parent=root)
    engine.log(LogLevel.INFO, "root work", trace=root)
    engine.log(LogLevel.INFO, "child work", trace=child)
    correlated = engine.trace(root.trace_id)
    assert correlated["record_count"] == 2
    assert correlated["span_count"] == 2
    assert any(span["parent_span_id"] == root.span_id for span in correlated["spans"])
    assert len(correlated["root_spans"]) == 1


def test_forbidden_log_fields_are_redacted():
    engine = ObservabilityEngine()
    trace = engine.start_trace("op.secret", "component.a")
    record = engine.log(
        LogLevel.WARN,
        "probe",
        trace=trace,
        fields={"api_key": "leak", "password": "leak", "component": "ok"},
    )
    assert record["fields"]["api_key"] == REDACTION_MARKER
    assert record["fields"]["password"] == REDACTION_MARKER
    assert record["fields"]["component"] == "ok"
    assert engine.redaction_scan()["ok"] is True


def test_redaction_walks_nested_structures():
    cleaned = redact({
        "outer": {"secret": "leak", "safe": 1},
        "rows": [{"token": "leak"}, {"safe": 2}],
    })
    assert cleaned["outer"]["secret"] == REDACTION_MARKER
    assert cleaned["outer"]["safe"] == 1
    assert cleaned["rows"][0]["token"] == REDACTION_MARKER
    assert cleaned["rows"][1]["safe"] == 2


def test_observability_declares_no_external_exporters(service: OperationsService):
    posture = service.observability.posture()
    assert posture["external_telemetry_providers"] == []
    assert posture["sink"] == "local_process_ring_buffer"
    assert set(posture["forbidden_telemetry_modules"]) == set(FORBIDDEN_TELEMETRY_MODULES)


def test_operation_timelines_and_execution_history(service: OperationsService):
    timelines = service.observability.timelines()
    assert timelines["count"] > 0
    history = service.observability.execution_history()
    assert history["order_execution_records"] == 0
    assert all(entry["order_execution"] is False for entry in history["history"])
    assert all(entry["provider_calls"] == 0 for entry in history["history"])


def test_audit_visualization_is_redacted_and_ordered(service: OperationsService):
    view = service.observability.audit_visualization(service.governance.store.list_audit(50))
    assert view["ok"] is True
    timestamps = [lane["created_at"] or 0 for lane in view["lanes"]]
    assert timestamps == sorted(timestamps)


def test_trace_lookup_for_unknown_id_is_rejected(service: OperationsService):
    with pytest.raises(OperationsError) as exc:
        service.observability.trace("trace_does_not_exist")
    assert exc.value.code is OperationsErrorCode.INVALID_REQUEST


def test_deterministic_clock_never_reads_wall_time():
    clock = DeterministicClock()
    assert clock.now() == clock.epoch
    clock.advance()
    assert clock.now() == clock.epoch + 0.25
    assert clock.snapshot()["wall_clock_used"] is False


# ── M330 metrics ────────────────────────────────────────────────────────────


def test_metrics_cover_every_required_kind(service: OperationsService):
    summary = service.metrics.summary()
    assert set(summary["covered_kinds"]) >= {kind.value for kind in MetricKind}
    assert summary["coverage_complete"] is True
    assert summary["missing_kinds"] == []


def test_required_metric_kinds_match_mission():
    assert {kind.value for kind in MetricKind} == {
        "api_latency", "task_duration", "queue_depth", "cache_performance",
        "replay_performance", "ui_performance", "database_performance",
    }


def test_percentile_is_nearest_rank_and_deterministic():
    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert percentile(values, 0.50) == 3.0
    assert percentile(values, 0.95) == 5.0
    assert percentile([], 0.95) == 0.0
    assert percentile(values, 0.95) == percentile(list(reversed(values)), 0.95)


def test_metric_classification_respects_direction():
    assert classify(MetricKind.API_LATENCY, 10.0) == "OK"
    assert classify(MetricKind.API_LATENCY, 300.0) == "WARNING"
    assert classify(MetricKind.API_LATENCY, 800.0) == "CRITICAL"
    # cache performance is a below-threshold metric
    assert METRIC_THRESHOLDS[MetricKind.CACHE_PERFORMANCE]["direction"] == "below"
    assert classify(MetricKind.CACHE_PERFORMANCE, 0.99) == "OK"
    assert classify(MetricKind.CACHE_PERFORMANCE, 0.70) == "WARNING"
    assert classify(MetricKind.CACHE_PERFORMANCE, 0.40) == "CRITICAL"


def test_metrics_summary_is_reproducible(service: OperationsService):
    assert service.metrics.summary()["fingerprint"] == service.metrics.summary()["fingerprint"]


def test_metrics_thresholds_are_advisory_only(service: OperationsService):
    summary = service.metrics.summary()
    assert summary["thresholds_are_advisory"] is True
    assert summary["autoscaling_triggered"] is False
    assert summary["cloud_monitoring_exporters"] == []


def test_metric_rejects_non_numeric_value():
    engine = MetricsEngine()
    with pytest.raises(OperationsError) as exc:
        engine.record(MetricKind.API_LATENCY, "tg.bad", "not-a-number")
    assert exc.value.code is OperationsErrorCode.INVALID_REQUEST


def test_metric_labels_are_redacted():
    engine = MetricsEngine()
    sample = engine.record(
        MetricKind.API_LATENCY, "tg.probe", 10.0, labels={"api_key": "leak", "route": "ok"},
    )["sample"]
    assert sample["labels"]["api_key"] == REDACTION_MARKER
    assert sample["labels"]["route"] == "ok"
    assert sample["cloud_exported"] is False


# ── M331 alerts ─────────────────────────────────────────────────────────────


def test_alert_severities_are_exactly_three():
    assert {item.value for item in AlertSeverity} == {
        "INFORMATIONAL", "WARNING", "CRITICAL",
    }


def test_alert_destinations_are_exactly_the_three_offline_sinks():
    assert {item.value for item in ALLOWED_DESTINATIONS} == {
        "control_center", "local_log", "audit_history",
    }


def test_alert_policy_forbids_external_transports(service: OperationsService):
    policy = service.alerts.destination_policy()
    assert set(policy["forbidden_destinations"]) == set(FORBIDDEN_ALERT_DESTINATIONS)
    for forbidden in ("email", "sms", "push", "webhook", "slack", "pagerduty"):
        assert forbidden in policy["forbidden_destinations"]
    assert policy["alerts_trigger_actions"] is False
    assert policy["alerts_grant_authority"] is False


@pytest.mark.parametrize("destination", ["email", "sms", "push", "webhook", "slack"])
def test_forbidden_alert_destination_is_rejected(service: OperationsService, destination: str):
    with pytest.raises(OperationsError) as exc:
        service.alerts.raise_alert(
            AlertSeverity.WARNING, "test.source", "probe", destinations=(destination,),
        )
    assert exc.value.code is OperationsErrorCode.FORBIDDEN_DESTINATION


def test_alert_lifecycle_open_acknowledge_resolve(service: OperationsService):
    alert = service.alerts.raise_alert(
        AlertSeverity.WARNING, "test.source", "lifecycle probe",
    )["alert"]
    assert alert["state"] == AlertState.OPEN.value
    assert service.alerts.acknowledge(alert["alert_id"])["alert"]["state"] == "ACKNOWLEDGED"
    assert service.alerts.resolve(alert["alert_id"])["alert"]["state"] == "RESOLVED"


def test_resolved_alert_is_terminal(service: OperationsService):
    alert = service.alerts.raise_alert(
        AlertSeverity.INFORMATIONAL, "test.source", "terminal probe",
    )["alert"]
    service.alerts.resolve(alert["alert_id"])
    with pytest.raises(OperationsError) as exc:
        service.alerts.acknowledge(alert["alert_id"])
    assert exc.value.code is OperationsErrorCode.ALERT_TRANSITION_INVALID


def test_unknown_alert_is_rejected(service: OperationsService):
    with pytest.raises(OperationsError) as exc:
        service.alerts.resolve("alert_missing")
    assert exc.value.code is OperationsErrorCode.ALERT_UNKNOWN


def test_alert_delivery_never_leaves_the_machine(service: OperationsService):
    service.alerts.raise_alert(AlertSeverity.CRITICAL, "test.source", "delivery probe")
    deliveries = service.alerts.deliveries()
    assert deliveries["external_deliveries"] == 0
    assert deliveries["network_deliveries"] == 0
    for delivery in deliveries["deliveries"]:
        assert delivery["network_used"] is False
        assert delivery["email_sent"] is False
        assert delivery["sms_sent"] is False
        assert delivery["push_sent"] is False
    assert service.alerts.isolation_scan()["ok"] is True


def test_alert_detail_is_redacted(service: OperationsService):
    alert = service.alerts.raise_alert(
        AlertSeverity.WARNING, "test.source", "redaction probe",
        detail={"api_key": "leak", "reason": "ok"},
    )["alert"]
    assert alert["detail"]["api_key"] == REDACTION_MARKER
    assert alert["detail"]["reason"] == "ok"
    assert alert["triggers_execution"] is False


def test_health_alerts_are_raised_without_remediation(service: OperationsService):
    service.health.force_state("platform.replay_engine", HealthState.DEGRADED)
    result = service.evaluate_health_alerts()
    assert result["raised_count"] >= 1
    assert result["remediation_triggered"] is False
    service.health.force_state("platform.replay_engine", None)


# ── M332 backup and recovery ────────────────────────────────────────────────


def test_backups_cover_every_required_kind(service: OperationsService):
    snapshots = service.backups.list_snapshots()
    assert set(snapshots["by_kind"]) == {kind.value for kind in BackupKind}
    assert snapshots["coverage_complete"] is True


def test_backup_targets_are_local_only(service: OperationsService):
    snapshots = service.backups.list_snapshots()
    assert snapshots["storage_target"] == "local_offline_store"
    assert snapshots["cloud_targets"] == []
    assert set(snapshots["forbidden_targets"]) == set(FORBIDDEN_BACKUP_TARGETS)
    for snapshot in snapshots["snapshots"]:
        assert snapshot["cloud_replicated"] is False
        assert snapshot["contains_credentials"] is False
        assert snapshot["contains_account_data"] is False


def test_backup_integrity_verifies(service: OperationsService):
    assert service.verify_backups()["ok"] is True


def test_recovery_simulation_never_mutates_live_state(service: OperationsService):
    result = service.simulate_recovery()
    recovery = result["recovery"]
    assert result["ok"] is True
    assert recovery["outcome"] == "SIMULATED_SUCCESS"
    assert recovery["live_state_mutated"] is False
    assert recovery["applied_to_production"] is False
    assert recovery["restored_credentials"] == 0
    assert recovery["restored_accounts"] == 0
    assert recovery["restored_orders"] == 0


def test_corrupted_snapshot_surfaces_integrity_mismatch():
    engine = BackupEngine()
    snapshot = engine.capture(
        BackupKind.CONFIGURATION, "drill", {"value": 1},
    )["snapshot"]
    assert engine.verify(snapshot["snapshot_id"])["ok"] is True
    engine.corrupt_for_drill(snapshot["snapshot_id"])
    assert engine.verify(snapshot["snapshot_id"])["ok"] is False
    result = engine.simulate_recovery(snapshot["snapshot_id"])
    assert result["ok"] is False
    assert result["recovery"]["outcome"] == "INTEGRITY_MISMATCH"


def test_snapshot_with_forbidden_field_is_rejected():
    engine = BackupEngine()
    with pytest.raises(OperationsError) as exc:
        engine.capture(BackupKind.CONFIGURATION, "leak", {"nested": {"api_key": "leak"}})
    assert exc.value.code is OperationsErrorCode.FORBIDDEN_FIELD


def test_unknown_snapshot_is_rejected(service: OperationsService):
    with pytest.raises(OperationsError) as exc:
        service.backups.simulate_recovery("snap_missing")
    assert exc.value.code is OperationsErrorCode.SNAPSHOT_UNKNOWN


def test_backup_isolation_scan_is_clean(service: OperationsService):
    scan = service.backups.isolation_scan()
    assert scan["ok"] is True
    assert scan["cloud_targets_configured"] == 0
    assert scan["remote_transports_present"] is False


# ── M333 diagnostics ────────────────────────────────────────────────────────


def test_diagnostics_cover_every_named_subsystem(service: OperationsService):
    report = service.run_diagnostics()
    assert set(report["covered_subsystems"]) == set(SUBSYSTEMS)
    assert report["missing_subsystems"] == []
    assert report["coverage_complete"] is True


def test_diagnostics_named_subsystems_match_mission():
    assert set(SUBSYSTEMS) == {
        "provider_contracts", "replay_engine", "authority_system", "approval_engine",
        "storage", "configuration", "browser_certification_history",
    }


def test_diagnostics_produce_one_unified_report(service: OperationsService):
    report = service.run_diagnostics()
    assert report["unified_report"] is True
    assert report["report_id"].startswith("diag_")
    assert report["ok"] is True
    assert report["failures"] == []


def test_diagnostics_are_deterministic(service: OperationsService):
    assert service.run_diagnostics()["report_digest"] == service.run_diagnostics()["report_digest"]


def test_diagnostics_never_remediate(service: OperationsService):
    report = service.run_diagnostics()
    assert report["auto_remediation"] is False
    for result in report["results"]:
        assert result["remediates_automatically"] is False


def test_diagnostics_statuses_are_bounded(service: OperationsService):
    valid = {status.value for status in DiagnosticStatus}
    for result in service.run_diagnostics()["results"]:
        assert result["status"] in valid


# ── M334 performance ────────────────────────────────────────────────────────


def test_load_validation_covers_every_required_dimension(service: OperationsService):
    report = service.run_load_validation()
    assert set(report["dimensions"]) == {
        "concurrent_users", "multiple_agents", "replay_workload",
        "dashboard_refresh", "api_concurrency",
    }
    assert report["coverage_complete"] is True


def test_load_validation_is_deterministically_repeatable():
    first = performance_module.run_all()
    second = performance_module.run_all()
    assert first["fingerprint"] == second["fingerprint"]
    proof = performance_module.prove_repeatability(4)
    assert proof["ok"] is True
    assert len(set(proof["fingerprints"])) == 1


def test_load_validation_generates_no_traffic(service: OperationsService):
    report = service.run_load_validation()
    for run in report["runs"]:
        assert run["simulation_only"] is True
        assert run["wall_clock_sleep_used"] is False
        assert run["network_requests_issued"] == 0
        assert run["orders_submitted"] == 0
        assert run["profile"]["real_network_calls"] == 0
        assert run["profile"]["real_threads_spawned"] == 0


def test_load_validation_stays_within_objectives(service: OperationsService):
    report = service.run_load_validation()
    assert report["breaches"] == []
    assert report["ok"] is True


def test_unknown_load_profile_is_rejected():
    with pytest.raises(OperationsError) as exc:
        performance_module.run_profile("load.does_not_exist")
    assert exc.value.code is OperationsErrorCode.LOAD_PROFILE_UNKNOWN


def test_repeatability_proof_requires_two_repetitions():
    with pytest.raises(OperationsError):
        performance_module.prove_repeatability(1)


# ── M335 control centre ─────────────────────────────────────────────────────


def test_control_center_exposes_every_required_panel(service: OperationsService):
    panels = service.control_center()["panels"]
    assert set(panels) == {
        "system_health", "metrics", "alerts", "diagnostics", "backups",
        "replay_health", "authority_summary", "certification_history",
    }


def test_control_center_is_read_only(service: OperationsService):
    control = service.control_center()
    assert control["execution_controls"] == 0
    assert control["deployment_controls"] == 0
    assert control["mutating_operational_controls"] == 0
    assert control["READ_ONLY_OPERATIONS_DASHBOARD"] is True
    assert set(control["allowed_ui_actions"]) == set(ALLOWED_UI_ACTIONS)


def test_control_center_forbids_execution_and_deployment_controls(service: OperationsService):
    forbidden = set(service.control_center()["forbidden_ui_controls"])
    assert set(FORBIDDEN_UI_CONTROLS) <= forbidden
    for control in (
        "order_form", "paper_order_form", "canary_activation", "deployment_control",
        "oauth_button", "login_button", "credential_input", "api_key_input",
        "restart_service_button", "execute_recovery_button",
    ):
        assert control in forbidden


def test_authority_summary_reports_all_locks_false(service: OperationsService):
    summary = service.authority_summary()
    assert summary["all_locks_false"] is True
    assert summary["deny_overrides_allow"] is True
    assert summary["authority_does_not_implicitly_expand"] is True
    assert summary["approval_activates_connectivity"] is False
    assert summary["operations_layer_grants_authority"] is False


def test_certification_history_is_read_only(service: OperationsService):
    history = service.certification_history()
    assert history["read_only"] is True
    assert history["history_mutated"] is False
    assert history["count"] > 0


# ── composition and isolation ───────────────────────────────────────────────


def test_charter_composes_existing_subsystems(service: OperationsService):
    charter = service.charter()
    assert charter["parallel_monitoring_systems_introduced"] == 0
    assert set(charter["composed_subsystems"]) >= {
        "governance", "authority", "approval", "certification", "replay",
        "provider_contracts", "audit", "evidence", "maturity",
    }
    assert charter["dashboard_is_read_only"] is True
    assert charter["recovery_is_simulation_only"] is True


def test_package_imports_no_network_or_telemetry_module():
    for path in sorted(PACKAGE_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            modules: list[str] = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = [node.module]
            for module in modules:
                if module.startswith("saathi."):
                    continue
                assert module.split(".", 1)[0] not in FORBIDDEN_NETWORK_IMPORTS, (
                    f"{path.name} imports {module}"
                )


def test_isolation_scan_is_clean(service: OperationsService):
    scan = service.isolation_scan()
    assert scan["ok"] is True
    assert scan["findings"] == []
    assert scan["network_clients"] == 0
    assert scan["telemetry_exporters"] == 0
    assert scan["email_transports"] == 0
    assert scan["sms_transports"] == 0
    assert scan["push_transports"] == 0
    assert scan["cloud_backup_clients"] == 0


def test_no_socket_is_opened_during_a_full_operations_cycle(service: OperationsService, monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("operations layer attempted a network connection")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    service.health.snapshot()
    service.metrics.summary()
    service.run_diagnostics()
    service.run_load_validation()
    service.verify_backups()
    service.simulate_recovery()
    service.control_center()


def test_security_scan_is_clean(service: OperationsService):
    scan = service.security_scan()
    assert scan["ok"] is True
    assert scan["findings"] == []
    assert scan["authority_locks_intact"] is True
    assert scan["provider_contract_security_ok"] is True
    assert scan["governance_security_ok"] is True


def test_predecessor_provider_contracts_remain_certified(service: OperationsService):
    assert service.provider_contracts.security_scan()["ok"] is True
    providers = service.provider_contracts.list_providers()
    assert providers["any_real"] is False
    assert providers["any_connected"] is False
    assert providers["any_authenticated"] is False


def test_maturity_ceiling_is_operationally_ready_offline(service: OperationsService):
    maturity = service.maturity()
    assert maturity["current"] == "OPERATIONALLY_READY_OFFLINE"
    assert maturity["max_state"] == "OPERATIONALLY_READY_OFFLINE"
    assert maturity["can_advance_automatically"] is False
    assert maturity["real_connectivity_ready"] is False
    assert maturity["production_deployment_ready"] is False
    assert maturity["next_state_requires_new_human_authority"] is True


# ── errors ──────────────────────────────────────────────────────────────────


def test_error_normalization_and_envelope():
    normalized = normalize_error(ValueError("bad"))
    assert normalized.code is OperationsErrorCode.INVALID_REQUEST
    assert normalize_error(RuntimeError("x")).code is OperationsErrorCode.INTERNAL
    envelope = error_envelope(ValueError("bad"))
    assert envelope["ok"] is False
    assert envelope["error"]["grants_authority"] is False
    assert envelope["LIVE_TRADING_AUTHORIZED"] is False


def test_service_safe_wrapper_normalizes(service: OperationsService):
    result = service.safe("simulate_recovery", "snap_missing")
    assert result["ok"] is False
    assert result["error"]["code"] == "snapshot_unknown"


# ── certification ───────────────────────────────────────────────────────────


def test_certification_reaches_the_terminal_verdict(service: OperationsService):
    result = service.certify()
    assert result["failures"] == []
    assert result["ok"] is True
    assert result["verdict"] == TERMINAL_VERDICT
    assert result["max_state"] == MAX_STATE
    assert result["current_maturity"] == CURRENT_MATURITY
    assert result["check_count"] >= 60


def test_certification_keeps_every_hard_lock_false(service: OperationsService):
    result = service.certify()
    for key in HARD_AUTHORITY_KEYS:
        assert result["hard_authority_locks"][key] is False
        assert result[key] is False


def test_certification_records_limitations(service: OperationsService):
    result = service.certify()
    assert len(result["limitations"]) >= 6
    joined = " ".join(result["limitations"]).lower()
    for phrase in ("no external telemetry", "simulated", "read-only", "no provider connectivity"):
        assert phrase in joined


def test_certification_is_audited(service: OperationsService):
    service.certify()
    kinds = {row["kind"] for row in service.governance.store.list_audit(100)}
    assert "operations_certify" in kinds


def test_evidence_bundle_is_complete(service: OperationsService):
    bundle = service.evidence_bundle()
    for key in (
        "posture", "charter", "health", "observability", "metrics", "alerts",
        "backups", "diagnostics", "load_validation", "control_center",
        "authority_summary", "certification_history", "security", "maturity",
    ):
        assert key in bundle
    assert bundle["evidence_hash"]


# ── API surface ─────────────────────────────────────────────────────────────


def test_operations_api_requires_authentication(api_client):
    client, _ = api_client
    assert client.get("/api/v1/platform/tg/operations/control-center").status_code in (401, 403)
    assert client.get("/api/v1/platform/tg/operations/health").status_code in (401, 403)


def test_operations_api_read_endpoints(api_client):
    client, headers = api_client
    for path in (
        "/api/v1/platform/tg/operations/posture",
        "/api/v1/platform/tg/operations/charter",
        "/api/v1/platform/tg/operations/control-center",
        "/api/v1/platform/tg/operations/health",
        "/api/v1/platform/tg/operations/observability",
        "/api/v1/platform/tg/operations/observability/timelines",
        "/api/v1/platform/tg/operations/observability/execution-history",
        "/api/v1/platform/tg/operations/observability/audit-visualization",
        "/api/v1/platform/tg/operations/metrics",
        "/api/v1/platform/tg/operations/alerts",
        "/api/v1/platform/tg/operations/alerts/policy",
        "/api/v1/platform/tg/operations/backups",
        "/api/v1/platform/tg/operations/backups/recovery-history",
        "/api/v1/platform/tg/operations/authority",
        "/api/v1/platform/tg/operations/certification-history",
        "/api/v1/platform/tg/operations/security",
        "/api/v1/platform/tg/operations/maturity",
    ):
        response = client.get(path, headers=headers)
        assert response.status_code == 200, path
        assert response.json()["ok"] is True, path


def test_operations_api_certify(api_client):
    client, headers = api_client
    response = client.post("/api/v1/platform/tg/operations/certify", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["verdict"] == TERMINAL_VERDICT


def test_operations_api_diagnostics_and_load(api_client):
    client, headers = api_client
    diagnostics = client.post("/api/v1/platform/tg/operations/diagnostics", headers=headers).json()
    assert diagnostics["ok"] is True
    load = client.post("/api/v1/platform/tg/operations/load-validation", headers=headers).json()
    assert load["ok"] is True
    assert load["repeatability"]["ok"] is True


def test_operations_api_backup_and_recovery(api_client):
    client, headers = api_client
    verify = client.post("/api/v1/platform/tg/operations/backups/verify", headers=headers).json()
    assert verify["ok"] is True
    recovery = client.post(
        "/api/v1/platform/tg/operations/backups/simulate-recovery",
        headers=headers,
        json={"snapshot_id": None},
    ).json()
    assert recovery["ok"] is True
    assert recovery["recovery"]["live_state_mutated"] is False


def test_operations_api_alert_lifecycle(api_client):
    client, headers = api_client
    alerts = client.get("/api/v1/platform/tg/operations/alerts", headers=headers).json()
    alert_id = alerts["alerts"][0]["alert_id"]
    acknowledged = client.post(
        f"/api/v1/platform/tg/operations/alerts/{alert_id}/acknowledge",
        headers=headers,
        json={"actor": "operator"},
    ).json()
    assert acknowledged["alert"]["state"] == "ACKNOWLEDGED"
    resolved = client.post(
        f"/api/v1/platform/tg/operations/alerts/{alert_id}/resolve",
        headers=headers,
        json={"actor": "operator"},
    ).json()
    assert resolved["alert"]["state"] == "RESOLVED"


def test_operations_api_normalizes_unknown_ids(api_client):
    client, headers = api_client
    body = client.post(
        "/api/v1/platform/tg/operations/alerts/alert_missing/resolve",
        headers=headers,
        json={"actor": "operator"},
    ).json()
    assert body["ok"] is False
    assert body["error"]["code"] == "alert_unknown"


def test_operations_api_exposes_no_execution_route(api_client):
    """The registered route table itself must contain no mutating operations path."""
    client, _ = api_client
    paths = {
        path for path in client.app.openapi()["paths"]
        if path.startswith("/api/v1/platform/tg/operations")
    }
    assert paths, "expected operations routes to be registered"
    for fragment in (
        "deploy", "restart", "scale", "connect", "login", "oauth", "credential",
        "order", "execute", "activate", "canary", "transfer", "withdraw", "kill",
    ):
        offending = [path for path in paths if fragment in path.lower()]
        assert not offending, (fragment, offending)


# ── UI boundary (static assertions) ─────────────────────────────────────────


def test_ui_pages_exist_for_every_panel():
    for relative in (
        "page.jsx", "health/page.jsx", "metrics/page.jsx",
        "alerts/page.jsx", "diagnostics/page.jsx", "backups/page.jsx",
    ):
        assert (UI_DIR / relative).exists(), relative


def _ui_sources() -> str:
    nav = Path(__file__).resolve().parents[1] / (
        "saathi-os/components/trading/OperationsNav.jsx"
    )
    return "\n".join(
        [path.read_text(encoding="utf-8") for path in sorted(UI_DIR.rglob("*.jsx"))]
        + [nav.read_text(encoding="utf-8")]
    )


def test_ui_exposes_no_credential_or_secret_input():
    """No text entry of any kind exists in the operations surface."""
    combined = _ui_sources()
    for element in ("<input", "<textarea", "<form", "type=\"password\""):
        assert element not in combined, element
    for field in FORBIDDEN_OBSERVABILITY_FIELDS:
        assert f'name="{field}"' not in combined
        assert f'placeholder="{field}"' not in combined


def test_ui_exposes_no_forbidden_action_label():
    """Button labels are the operator-visible controls; none may be mutating."""
    import re

    # Button attributes span lines and contain '>' inside onClick handlers, so match
    # only the leaf text immediately preceding the closing tag.
    labels = {
        label.strip().lower()
        for label in re.findall(r">([^<>{}]+)</Button>", _ui_sources())
        if label.strip()
    }
    assert labels, "expected the operations UI to declare buttons"
    allowed = {
        "load operations posture", "run operations certification", "load system health",
        "load metrics summary", "run offline load validation", "load alert history",
        "load destination policy", "acknowledge", "resolve",
        "run offline diagnostics", "load certification history", "load snapshots",
        "verify snapshot integrity", "simulate recovery",
    }
    assert labels <= allowed, labels - allowed
    for forbidden in (
        "connect", "login", "log in", "sign in to broker", "deploy", "restart",
        "scale", "place order", "submit order", "transfer", "withdraw",
        "activate canary", "go live", "start trading", "execute recovery",
    ):
        assert not any(forbidden in label for label in labels), forbidden


def test_ui_renders_the_boundary_and_authority_rails():
    combined = _ui_sources()
    for statement in (
        "OFFLINE OPERATIONS DATA",
        "READ-ONLY DASHBOARD",
        "NO EXECUTION CONTROLS",
        "NO DEPLOYMENT CONTROLS",
        "NO EXTERNAL TELEMETRY",
        "NO CLOUD MONITORING",
        "NO CLOUD BACKUP",
        "NO EMAIL, SMS, OR PUSH ALERTING",
    ):
        assert statement in combined, statement
    for key in HARD_AUTHORITY_KEYS:
        assert f"{key}=false" in combined, key
    assert "OPERATIONALLY_READY_OFFLINE" in combined
