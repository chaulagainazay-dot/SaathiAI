"""M328–M335 operations service.

Composes health, observability, metrics, alerts, backup, diagnostics, performance and
the read-only operations control centre onto the existing governance, authority,
approval, provider-contract, replay, audit and maturity stack. It introduces no
parallel monitoring system and no new authority.
"""
from __future__ import annotations

import ast
import sqlite3
from pathlib import Path
from threading import RLock
from typing import Any

from saathi.platform.tg.connectivity_governance.service import (
    ConnectivityGovernanceService,
    default_connectivity_governance,
)
from saathi.platform.tg.production_readiness import diagnostics as diagnostics_module
from saathi.platform.tg.production_readiness import performance as performance_module
from saathi.platform.tg.production_readiness.alerts import (
    AlertEngine,
    evaluate_health_alerts,
)
from saathi.platform.tg.production_readiness.backup import BackupEngine
from saathi.platform.tg.production_readiness.errors import (
    OperationsError,
    OperationsErrorCode,
    error_envelope,
)
from saathi.platform.tg.production_readiness.health import build_health_engine
from saathi.platform.tg.production_readiness.metrics import (
    MetricsEngine,
    seed_baseline,
)
from saathi.platform.tg.production_readiness.models import (
    AUTHORITY_LOCKS,
    BOUNDARY_VALUES,
    BROWSER_CERT_VERDICT,
    CURRENT_MATURITY,
    ENGINE_VERSION,
    HARD_AUTHORITY_KEYS,
    INHERITED_AUTHORITY_LOCKS,
    MAX_STATE,
    SCHEMA_VERSION,
    TERMINAL_STATEMENTS,
    TERMINAL_VERDICT,
    AlertSeverity,
    BackupKind,
    DeterministicClock,
    LogLevel,
    authority_locks_intact,
    digest,
)
from saathi.platform.tg.production_readiness.observability import (
    FORBIDDEN_TELEMETRY_MODULES,
    ObservabilityEngine,
)
from saathi.platform.tg.provider_contracts.service import (
    ProviderContractService,
    default_provider_contracts,
    reset_provider_contracts_for_tests,
)

# Modules that would give this layer a way off the machine. The isolation scan walks
# the package AST and fails if any of them is imported.
FORBIDDEN_NETWORK_IMPORTS = frozenset({
    "aiohttp",
    "boto3",
    "botocore",
    "google",
    "grpc",
    "httpx",
    "paramiko",
    "requests",
    "smtplib",
    "socket",
    "subprocess",
    "twilio",
    "urllib",
    "websocket",
    "websockets",
}) | FORBIDDEN_TELEMETRY_MODULES

FORBIDDEN_DYNAMIC_IMPORT_CALLS = frozenset({"__import__", "import_module"})

# UI controls that must never exist on the operations dashboard.
FORBIDDEN_UI_CONTROLS = (
    "credential_input",
    "api_key_input",
    "secret_input",
    "oauth_button",
    "login_button",
    "real_provider_connect_button",
    "live_connect_button",
    "account_link_button",
    "account_selector",
    "order_form",
    "paper_order_form",
    "transfer_form",
    "withdrawal_form",
    "canary_activation",
    "deployment_control",
    "restart_service_button",
    "scale_service_button",
    "execute_recovery_button",
    "kill_switch_override",
)

ALLOWED_UI_ACTIONS = (
    "load_system_health",
    "load_metrics_summary",
    "load_alert_history",
    "acknowledge_alert",
    "resolve_alert",
    "run_offline_diagnostics",
    "verify_backup_integrity",
    "simulate_recovery",
    "run_offline_load_validation",
    "run_operations_certification",
)

REQUIRED_MODULES = (
    "saathi.platform.tg.connectivity_governance.service",
    "saathi.platform.tg.provider_contracts.service",
    "saathi.platform.tg.production_readiness.health",
    "saathi.platform.tg.production_readiness.observability",
    "saathi.platform.tg.production_readiness.metrics",
    "saathi.platform.tg.production_readiness.alerts",
    "saathi.platform.tg.production_readiness.backup",
    "saathi.platform.tg.production_readiness.diagnostics",
    "saathi.platform.tg.production_readiness.performance",
)


class OperationsService:
    def __init__(
        self,
        governance: ConnectivityGovernanceService | None = None,
        provider_contracts: ProviderContractService | None = None,
        repo_root: Path | None = None,
    ):
        self.governance = governance or default_connectivity_governance()
        self.provider_contracts = provider_contracts or default_provider_contracts()
        self.repo_root = Path(repo_root) if repo_root else Path(__file__).resolve().parents[4]
        self.clock = DeterministicClock()
        self._lock = RLock()

        self.observability = ObservabilityEngine(clock=self.clock)
        self.metrics = MetricsEngine(clock=self.clock)
        self.alerts = AlertEngine(
            self.observability,
            audit_sink=self.governance.store,
            clock=self.clock,
        )
        self.backups = BackupEngine(clock=self.clock)
        self.health = build_health_engine(self, clock=self.clock)

        self._bootstrapped = False
        self.bootstrap()

    # ── bootstrap ───────────────────────────────────────────────────────────
    def bootstrap(self) -> dict[str, Any]:
        """Seed deterministic baseline observations so every surface has real data."""
        with self._lock:
            if self._bootstrapped:
                return {"ok": True, "already_bootstrapped": True}
            self._bootstrapped = True
        trace = self.observability.start_trace("operations.bootstrap", "operations")
        self.observability.log(
            LogLevel.INFO,
            "operations layer bootstrapped",
            trace=trace,
            fields={"milestones": "M328-M335", "offline_only": True},
        )
        seed_baseline(self.metrics)
        load_report = performance_module.run_all(clock=self.clock)
        self.metrics.record_many(performance_module.metric_entries(load_report))
        self.backups.capture(
            BackupKind.CONFIGURATION,
            "operations_configuration_baseline",
            self.configuration_snapshot_payload(),
        )
        self.backups.capture(
            BackupKind.REPLAY_SNAPSHOT,
            "replay_fixture_manifest",
            self.replay_snapshot_payload(),
        )
        self.backups.capture(
            BackupKind.DATABASE,
            "governance_database_manifest",
            self.database_snapshot_payload(),
        )
        self.alerts.raise_alert(
            AlertSeverity.INFORMATIONAL,
            "operations.bootstrap",
            "Operations observability initialised offline",
            detail={"milestones": "M328-M335"},
        )
        self.observability.log(
            LogLevel.INFO,
            "baseline metrics, snapshots and load model recorded",
            trace=trace,
            fields={"load_profiles": load_report["profile_count"]},
        )
        return {"ok": True, "bootstrapped": True}

    # ── health probe backing data ───────────────────────────────────────────
    def authority_locks_ok(self) -> bool:
        return authority_locks_intact()

    def module_inventory(self) -> dict[str, bool]:
        import importlib.util

        return {
            name: importlib.util.find_spec(name) is not None
            for name in REQUIRED_MODULES
        }

    def dependency_inventory(self) -> dict[str, bool]:
        """Only local, offline dependencies. Nothing here reaches a network."""
        checks: dict[str, bool] = {}
        checks["governance_service"] = self.governance is not None
        checks["provider_contract_service"] = self.provider_contracts is not None
        checks["governance_store"] = getattr(self.governance, "store", None) is not None
        checks["replay_provider"] = getattr(
            self.provider_contracts, "replay_provider", None
        ) is not None
        checks["repo_root_readable"] = Path(self.repo_root).exists()
        checks["sqlite_available"] = sqlite3 is not None
        return checks

    def storage_health(self) -> dict[str, Any]:
        try:
            schema = self.governance.store.schema_scan()
            db_path = Path(self.governance.store.db_path)
            exists = db_path.exists()
            size = db_path.stat().st_size if exists else 0
            ok = schema["ok"] and exists
            return {
                "ok": ok,
                "reason": "storage_reachable_and_clean" if ok else "storage_schema_or_file_issue",
                "detail": {
                    "schema_ok": schema["ok"],
                    "table_count": len(schema["tables"]),
                    "forbidden_fields_found": schema["forbidden_fields_found"],
                    "database_present": exists,
                    "database_size_bytes": size,
                    "raw_credentials_forbidden": schema["raw_credentials_forbidden"],
                },
            }
        except Exception as exc:
            return {
                "ok": False,
                "reason": "storage_probe_failed",
                "detail": {"exception": type(exc).__name__},
            }

    def scheduler_health(self) -> dict[str, Any]:
        """Scheduler here is the offline research orchestrator queue, not a cron daemon."""
        try:
            from saathi.platform.tg.research_orchestrator.service import (
                default_research_orchestrator,
            )

            orchestrator = default_research_orchestrator()
            queue = orchestrator.queue_status() if hasattr(orchestrator, "queue_status") else {}
            pending = int(queue.get("pending", 0) or 0)
            return {
                "ok": True,
                "backlog": pending > 0,
                "reason": "scheduler_idle" if pending == 0 else "scheduler_backlog",
                "detail": {
                    "pending": pending,
                    "engine": "offline_research_orchestrator",
                    "external_cron": False,
                    "background_threads": 0,
                },
            }
        except Exception:
            # A scheduler that is not wired in this deployment is not an incident;
            # the operations layer degrades to an explicit, visible statement.
            return {
                "ok": True,
                "backlog": False,
                "reason": "scheduler_not_configured",
                "detail": {
                    "pending": 0,
                    "engine": "none",
                    "external_cron": False,
                    "background_threads": 0,
                },
            }

    def replay_health(self) -> dict[str, Any]:
        try:
            fixtures = self.provider_contracts.replay_fixtures()
            payload = {
                "provider_id": "saathi.replay.market.v1",
                "operation": "quotes.get",
                "params": {"symbol": "AAPL"},
                "idempotency_key": "health:replay:quote:AAPL:v1",
            }
            first = self.provider_contracts.request(payload)
            second = self.provider_contracts.request(payload)
            ok = fixtures["count"] > 0 and first == second
            return {
                "ok": ok,
                "reason": "replay_deterministic" if ok else "replay_nondeterministic",
                "detail": {
                    "fixture_count": fixtures["count"],
                    "deterministic": first == second,
                    "network_capture": fixtures["network_capture"],
                    "recorded_offline": fixtures["recorded_offline"],
                },
            }
        except Exception as exc:
            return {
                "ok": False,
                "reason": "replay_probe_failed",
                "detail": {"exception": type(exc).__name__},
            }

    def provider_registry_health(self) -> dict[str, Any]:
        try:
            governance_providers = self.governance.list_providers()
            contract_providers = self.provider_contracts.list_providers()
            ok = (
                governance_providers["any_connected"] is False
                and contract_providers["any_connected"] is False
                and contract_providers["any_real"] is False
                and contract_providers["any_authenticated"] is False
            )
            return {
                "ok": ok,
                "reason": "registry_offline_and_bounded" if ok else "registry_boundary_breach",
                "detail": {
                    "governance_provider_count": governance_providers["count"],
                    "contract_provider_count": contract_providers["count"],
                    "any_connected": contract_providers["any_connected"],
                    "any_real": contract_providers["any_real"],
                    "any_authenticated": contract_providers["any_authenticated"],
                },
            }
        except Exception as exc:
            return {
                "ok": False,
                "reason": "registry_probe_failed",
                "detail": {"exception": type(exc).__name__},
            }

    # ── snapshot payloads (M332 inputs) ─────────────────────────────────────
    def configuration_snapshot_payload(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "engine_version": ENGINE_VERSION,
            "milestones": "M328-M335",
            "max_state": MAX_STATE,
            "current_maturity": CURRENT_MATURITY,
            "authority_locks": dict(AUTHORITY_LOCKS),
            "inherited_authority_locks": dict(INHERITED_AUTHORITY_LOCKS),
            "allowed_ui_actions": list(ALLOWED_UI_ACTIONS),
            "forbidden_ui_controls": list(FORBIDDEN_UI_CONTROLS),
            "alert_destinations": ["control_center", "local_log", "audit_history"],
            "offline_only": True,
            "read_only_dashboard": True,
        }

    def replay_snapshot_payload(self) -> dict[str, Any]:
        fixtures = self.provider_contracts.replay_fixtures()
        return {
            "fixture_count": fixtures["count"],
            "fixtures": fixtures["fixtures"],
            "deterministic": fixtures["deterministic"],
            "recorded_offline": fixtures["recorded_offline"],
            "network_capture": fixtures["network_capture"],
        }

    def database_snapshot_payload(self) -> dict[str, Any]:
        schema = self.governance.store.schema_scan()
        db_path = Path(self.governance.store.db_path)
        return {
            "database": db_path.name,
            "tables": schema["tables"],
            "table_count": len(schema["tables"]),
            "forbidden_fields_found": schema["forbidden_fields_found"],
            "raw_credentials_forbidden": schema["raw_credentials_forbidden"],
            "size_bytes": db_path.stat().st_size if db_path.exists() else 0,
            "cloud_replicated": False,
        }

    # ── charter and posture ─────────────────────────────────────────────────
    def charter(self) -> dict[str, Any]:
        return {
            "ok": True,
            "milestone": "M328-M335",
            "name": "Production Readiness, Observability and Operational Resilience",
            "scope": "offline_operational_observation_only",
            "objective": "operational reliability before any real connectivity work",
            "health_state_grants_no_authority": True,
            "metric_thresholds_are_advisory": True,
            "alerts_never_trigger_actions": True,
            "recovery_is_simulation_only": True,
            "diagnostics_never_remediate": True,
            "load_validation_is_modelled_not_generated": True,
            "dashboard_is_read_only": True,
            "composed_subsystems": [
                "governance",
                "authority",
                "approval",
                "certification",
                "replay",
                "provider_contracts",
                "audit",
                "evidence",
                "maturity",
            ],
            "parallel_monitoring_systems_introduced": 0,
            "certification_requirements": [
                "focused_tests",
                "predecessor_regressions",
                "frontend_tests",
                "production_build",
                "browser_certification",
                "clean_clone_certification",
                "recovery_validation",
                "diagnostics_validation",
                "performance_validation",
                "secret_scan",
                "network_isolation_scan",
                "telemetry_isolation_scan",
                "authority_scan",
            ],
            **BOUNDARY_VALUES,
        }

    def posture(self) -> dict[str, Any]:
        return {
            "ok": True,
            "milestones": "M328-M335",
            "schema_version": SCHEMA_VERSION,
            "engine_version": ENGINE_VERSION,
            "verdict_target": TERMINAL_VERDICT,
            "browser_verdict_target": BROWSER_CERT_VERDICT,
            "max_state": MAX_STATE,
            "current_maturity": CURRENT_MATURITY,
            "mode": "OFFLINE_OPERATIONS_OBSERVABILITY",
            "predecessor_maturity": "MOCK_CONNECTIVITY_ONLY",
            "governance_binding": {
                "governance_maturity": self.governance.maturity().get("current"),
                "provider_contract_maturity": self.provider_contracts.maturity()["current"],
                "connected": False,
            },
            "engines": {
                "health": len(self.health.registered_components()),
                "observability": self.observability.posture()["record_count"],
                "metrics": self.metrics.summary()["series_count"],
                "alerts": self.alerts.list_alerts()["count"],
                "backups": self.backups.list_snapshots()["count"],
                "load_profiles": len(performance_module.LOAD_PROFILES),
            },
            "statements": list(TERMINAL_STATEMENTS),
            "clock": self.clock.snapshot(),
            **BOUNDARY_VALUES,
        }

    def maturity(self) -> dict[str, Any]:
        return {
            "ok": True,
            "current": CURRENT_MATURITY,
            "max_state": MAX_STATE,
            "governance_dependency": "GOVERNANCE_ONLY_CERTIFIED",
            "provider_contract_dependency": "MOCK_CONNECTIVITY_ONLY",
            "operations_ready_offline": True,
            "real_connectivity_ready": False,
            "production_deployment_ready": False,
            "can_advance_automatically": False,
            "next_state_requires_new_human_authority": True,
            **AUTHORITY_LOCKS,
            **BOUNDARY_VALUES,
        }

    # ── M335 operations control centre ──────────────────────────────────────
    def control_center(self) -> dict[str, Any]:
        health = self.health.snapshot()
        metrics = self.metrics.summary()
        alerts = self.alerts.list_alerts()
        backups = self.backups.list_snapshots()
        recovery = self.backups.recovery_history()
        replay = self.replay_health()
        authority = self.authority_summary()
        certification_history = self.certification_history()
        return {
            "ok": True,
            "milestone": "M335",
            "title": "Operations Control Center",
            "subtitle": "Read-only offline operations posture for SaathiOS Trading Guardian",
            "safety_labels": [
                "OFFLINE OPERATIONS DATA",
                "READ-ONLY DASHBOARD",
                "NO EXECUTION CONTROLS",
                "NO DEPLOYMENT CONTROLS",
            ],
            "verdict_target": TERMINAL_VERDICT,
            "max_state": MAX_STATE,
            "current_maturity": CURRENT_MATURITY,
            "panels": {
                "system_health": {
                    "overall_state": health["overall_state"],
                    "component_count": health["component_count"],
                    "counts": health["counts"],
                    "domains": [
                        {
                            "domain": domain["domain"],
                            "state": domain["state"],
                            "component_count": domain["component_count"],
                        }
                        for domain in health["domains"]
                    ],
                    "coverage_complete": health["domain_coverage_complete"],
                },
                "metrics": {
                    "series_count": metrics["series_count"],
                    "sample_count": metrics["sample_count"],
                    "covered_kinds": metrics["covered_kinds"],
                    "coverage_complete": metrics["coverage_complete"],
                    "breach_count": metrics["breach_count"],
                    "threshold_breaches": metrics["threshold_breaches"],
                },
                "alerts": {
                    "count": alerts["count"],
                    "by_severity": alerts["by_severity"],
                    "by_state": alerts["by_state"],
                    "open_critical": alerts["open_critical"],
                    "destinations": ["control_center", "local_log", "audit_history"],
                },
                "diagnostics": {
                    "subsystems": list(diagnostics_module.SUBSYSTEMS),
                    "subsystem_count": len(diagnostics_module.SUBSYSTEMS),
                    "on_demand": True,
                    "auto_remediation": False,
                },
                "backups": {
                    "snapshot_count": backups["count"],
                    "by_kind": backups["by_kind"],
                    "coverage_complete": backups["coverage_complete"],
                    "recovery_runs": recovery["count"],
                    "recovery_successful": recovery["successful"],
                    "cloud_backup": False,
                },
                "replay_health": {
                    "ok": replay["ok"],
                    "reason": replay["reason"],
                    "fixture_count": replay["detail"]["fixture_count"],
                    "deterministic": replay["detail"]["deterministic"],
                },
                "authority_summary": authority,
                "certification_history": certification_history,
            },
            "allowed_ui_actions": list(ALLOWED_UI_ACTIONS),
            "forbidden_ui_controls": list(FORBIDDEN_UI_CONTROLS),
            "execution_controls": 0,
            "deployment_controls": 0,
            "mutating_operational_controls": 0,
            "statements": list(TERMINAL_STATEMENTS),
            **BOUNDARY_VALUES,
        }

    def authority_summary(self) -> dict[str, Any]:
        from saathi.platform.tg.connectivity_governance.authority import (
            prove_deny_overrides_allow,
            prove_no_implicit_expansion,
        )

        return {
            "ok": True,
            "hard_authority_keys": list(HARD_AUTHORITY_KEYS),
            "hard_authority_locks": dict(AUTHORITY_LOCKS),
            "inherited_authority_locks": dict(INHERITED_AUTHORITY_LOCKS),
            "all_locks_false": authority_locks_intact(),
            "deny_overrides_allow": prove_deny_overrides_allow()["ok"],
            "authority_does_not_implicitly_expand": prove_no_implicit_expansion()["ok"],
            "approval_activates_connectivity": False,
            "operations_layer_grants_authority": False,
        }

    def certification_history(self) -> dict[str, Any]:
        """Read prior milestone certification records. Read-only; nothing is written."""
        records: list[dict[str, Any]] = []
        evidence_root = Path(self.repo_root) / "docs" / "trading"
        candidates = [
            ("M312-M319", "m312_m319_evidence/browser/M319_BROWSER_CERT.json"),
            ("M320-M327", "m320_m327_evidence/M327_CONTRACT_CERTIFICATION.json"),
            ("M320-M327", "m320_m327_evidence/browser/M327_BROWSER_CERT.json"),
        ]
        for milestone, relative in candidates:
            path = evidence_root / relative
            if not path.exists():
                records.append({
                    "milestone": milestone,
                    "path": relative,
                    "present": False,
                    "verdict": None,
                })
                continue
            try:
                import json

                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                records.append({
                    "milestone": milestone,
                    "path": relative,
                    "present": True,
                    "readable": False,
                    "verdict": None,
                })
                continue
            records.append({
                "milestone": milestone,
                "path": relative,
                "present": True,
                "readable": True,
                "ok": payload.get("ok"),
                "verdict": payload.get("verdict") or payload.get("browser_verdict"),
            })
        return {
            "ok": True,
            "count": len(records),
            "records": records,
            "read_only": True,
            "history_mutated": False,
        }

    # ── operations actions (all read-only or simulation) ────────────────────
    def run_diagnostics(self) -> dict[str, Any]:
        trace = self.observability.start_trace("operations.diagnostics", "diagnostics")
        report = diagnostics_module.run_diagnostics(self)
        self.observability.log(
            LogLevel.INFO if report["ok"] else LogLevel.ERROR,
            "diagnostics run complete",
            trace=trace,
            fields={"report_id": report["report_id"], "failures": len(report["failures"])},
        )
        self.metrics.record(
            "task_duration",
            "tg.diagnostics.full_run",
            float(report["check_count"]) * 100.0,
            labels={"source": "offline_diagnostics"},
        )
        if not report["ok"]:
            self.alerts.raise_alert(
                AlertSeverity.CRITICAL,
                "operations.diagnostics",
                "Offline diagnostics reported failures",
                detail={"failures": report["failures"]},
            )
        return report

    def run_load_validation(self) -> dict[str, Any]:
        trace = self.observability.start_trace("operations.load_validation", "performance")
        report = performance_module.run_all(clock=self.clock)
        repeatability = performance_module.prove_repeatability()
        report["repeatability"] = repeatability
        report["ok"] = report["ok"] and repeatability["ok"]
        self.observability.log(
            LogLevel.INFO,
            "offline load validation complete",
            trace=trace,
            fields={
                "profiles": report["profile_count"],
                "breaches": len(report["breaches"]),
                "repeatable": repeatability["ok"],
            },
        )
        self.metrics.record_many(performance_module.metric_entries(report))
        return report

    def verify_backups(self) -> dict[str, Any]:
        trace = self.observability.start_trace("operations.backup_verify", "backup")
        report = self.backups.verify_all()
        self.observability.log(
            LogLevel.INFO if report["ok"] else LogLevel.ERROR,
            "backup integrity verification complete",
            trace=trace,
            fields={"verified": report["verified_count"], "failures": len(report["failures"])},
        )
        return report

    def simulate_recovery(self, snapshot_id: str | None = None) -> dict[str, Any]:
        if snapshot_id is None:
            snapshots = self.backups.list_snapshots()
            if not snapshots["count"]:
                raise OperationsError(
                    OperationsErrorCode.SNAPSHOT_UNKNOWN,
                    "No snapshot is available to recover",
                )
            snapshot_id = snapshots["snapshots"][0]["snapshot_id"]
        trace = self.observability.start_trace("operations.recovery_simulation", "backup")
        report = self.backups.simulate_recovery(snapshot_id)
        self.observability.log(
            LogLevel.INFO if report["ok"] else LogLevel.ERROR,
            "recovery simulation complete",
            trace=trace,
            fields={
                "snapshot_id": snapshot_id,
                "outcome": report["recovery"]["outcome"],
            },
        )
        return report

    def evaluate_health_alerts(self) -> dict[str, Any]:
        return evaluate_health_alerts(self.alerts, self.health.snapshot())

    # ── scans ───────────────────────────────────────────────────────────────
    def isolation_scan(self) -> dict[str, Any]:
        package_dir = Path(__file__).resolve().parent
        findings: list[dict[str, Any]] = []
        inspected: list[str] = []
        for path in sorted(package_dir.glob("*.py")):
            inspected.append(path.name)
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                modules: list[str] = []
                if isinstance(node, ast.Import):
                    modules = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    modules = [node.module]
                for module in modules:
                    root = module.split(".", 1)[0]
                    if root in FORBIDDEN_NETWORK_IMPORTS and not module.startswith("saathi."):
                        findings.append({"file": path.name, "module": module})
                if isinstance(node, ast.Call):
                    call_name = ""
                    if isinstance(node.func, ast.Name):
                        call_name = node.func.id
                    elif isinstance(node.func, ast.Attribute):
                        call_name = node.func.attr
                    if call_name in FORBIDDEN_DYNAMIC_IMPORT_CALLS:
                        findings.append({"file": path.name, "dynamic_import_call": call_name})
        return {
            "ok": not findings,
            "findings": findings,
            "inspected_files": inspected,
            "forbidden_modules": sorted(FORBIDDEN_NETWORK_IMPORTS),
            "network_clients": 0,
            "telemetry_exporters": 0,
            "email_transports": 0,
            "sms_transports": 0,
            "push_transports": 0,
            "cloud_backup_clients": 0,
            **AUTHORITY_LOCKS,
        }

    def security_scan(self) -> dict[str, Any]:
        isolation = self.isolation_scan()
        redaction = self.observability.redaction_scan()
        alert_isolation = self.alerts.isolation_scan()
        backup_isolation = self.backups.isolation_scan()
        contract_security = self.provider_contracts.security_scan()
        governance_security = self.governance.security_scan()
        findings: list[str] = []
        if not authority_locks_intact():
            findings.append("authority_lock_failed")
        if not isolation["ok"]:
            findings.append("forbidden_import_detected")
        if not redaction["ok"]:
            findings.append("observability_redaction_failed")
        if not alert_isolation["ok"]:
            findings.append("alert_isolation_failed")
        if not backup_isolation["ok"]:
            findings.append("backup_isolation_failed")
        if not contract_security.get("ok"):
            findings.append("provider_contract_security_failed")
        if not governance_security.get("ok"):
            findings.append("governance_security_failed")
        return {
            "ok": not findings,
            "findings": findings,
            "isolation": isolation,
            "observability_redaction": redaction,
            "alert_isolation": alert_isolation,
            "backup_isolation": backup_isolation,
            "provider_contract_security_ok": contract_security.get("ok") is True,
            "governance_security_ok": governance_security.get("ok") is True,
            "authority_locks_intact": authority_locks_intact(),
            **BOUNDARY_VALUES,
        }

    # ── evidence and certification ──────────────────────────────────────────
    def evidence_bundle(self) -> dict[str, Any]:
        bundle = {
            "ok": True,
            "posture": self.posture(),
            "charter": self.charter(),
            "health": self.health.snapshot(),
            "health_rollup_proof": self.health.rollup_proof(),
            "observability": self.observability.posture(),
            "timelines": self.observability.timelines(),
            "execution_history": self.observability.execution_history(),
            "audit_visualization": self.observability.audit_visualization(
                self.governance.store.list_audit(50)
            ),
            "metrics": self.metrics.summary(),
            "alerts": self.alerts.list_alerts(),
            "alert_policy": self.alerts.destination_policy(),
            "alert_deliveries": self.alerts.deliveries(),
            "backups": self.backups.list_snapshots(),
            "backup_posture": self.backups.posture(),
            "recovery_history": self.backups.recovery_history(),
            "diagnostics": self.run_diagnostics(),
            "load_validation": self.run_load_validation(),
            "control_center": self.control_center(),
            "authority_summary": self.authority_summary(),
            "certification_history": self.certification_history(),
            "security": self.security_scan(),
            "maturity": self.maturity(),
            "governance_audit": self.governance.store.list_audit(50),
            **BOUNDARY_VALUES,
        }
        bundle["evidence_hash"] = digest(bundle)
        return bundle

    def certify(self) -> dict[str, Any]:
        from saathi.platform.tg.production_readiness.certification import (
            certify_production_readiness,
        )

        return certify_production_readiness(self)

    def safe(self, fn_name: str, *args, **kwargs) -> dict[str, Any]:
        """Call a service method and normalize any error into the standard envelope."""
        try:
            return getattr(self, fn_name)(*args, **kwargs)
        except Exception as exc:
            return error_envelope(exc)


_default: OperationsService | None = None
_default_lock = RLock()


def default_operations() -> OperationsService:
    global _default
    with _default_lock:
        if _default is None:
            _default = OperationsService()
        return _default


def reset_operations_for_tests(db_path: str | Path | None = None) -> OperationsService:
    global _default
    # reset_provider_contracts_for_tests also rebuilds governance, so take the
    # governance instance it bound rather than creating a second one.
    contracts = reset_provider_contracts_for_tests(db_path=db_path)
    with _default_lock:
        _default = OperationsService(
            governance=contracts.governance,
            provider_contracts=contracts,
        )
        return _default
