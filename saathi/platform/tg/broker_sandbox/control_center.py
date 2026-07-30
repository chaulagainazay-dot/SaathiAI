"""M223 — Sandbox Control Center read model.

Surfaces: Broker Registry, Capability Viewer, Sandbox Emulator, Trust Center,
Approval Pipeline, Credential Metadata, Recovery Center, Audit Timeline,
Security Dashboard. Everything labelled SANDBOX ONLY / NO LIVE BROKER.
"""
from __future__ import annotations

from typing import Any

from saathi.platform.tg.broker_sandbox.abstraction import abstraction_surface
from saathi.platform.tg.broker_sandbox.credentials import CredentialTrustFramework
from saathi.platform.tg.broker_sandbox.emulator import SandboxEmulator
from saathi.platform.tg.broker_sandbox.failure import FailureRecoverySimulator
from saathi.platform.tg.broker_sandbox.models import (
    ENGINE_VERSION,
    LLM_BOUNDARY,
    PAPER_POSTURE,
    SCHEMA_VERSION,
    TERMINAL_VERDICT,
)
from saathi.platform.tg.broker_sandbox.registry import CapabilityRegistry
from saathi.platform.tg.broker_sandbox.security import SecurityValidator
from saathi.platform.tg.broker_sandbox.store import SandboxStore
from saathi.platform.tg.broker_sandbox.trust_pipeline import TrustApprovalPipeline


class SandboxControlCenter:
    def __init__(
        self,
        store: SandboxStore,
        registry: CapabilityRegistry,
        credentials: CredentialTrustFramework,
        trust: TrustApprovalPipeline,
        emulator: SandboxEmulator,
        failure: FailureRecoverySimulator,
        security: SecurityValidator,
    ):
        self.store = store
        self.registry = registry
        self.credentials = credentials
        self.trust = trust
        self.emulator = emulator
        self.failure = failure
        self.security = security

    def labels(self) -> dict[str, str]:
        return {
            "sandbox_only": "SANDBOX ONLY",
            "no_live_broker": "NO LIVE BROKER",
            "paper_only": "PAPER ONLY",
            "no_live_trading": "NO LIVE TRADING",
            "no_api_credentials": "NO API CREDENTIALS",
            "no_real_orders": "SANDBOX CANNOT EXECUTE REAL ORDERS",
        }

    def overview(self) -> dict[str, Any]:
        brokers = self.registry.list_brokers()
        caps = self.registry.list_capabilities()
        creds = self.credentials.list_references()
        pipes = self.trust.list_pipelines()
        audit = self.store.list_audit(limit=30)
        failures = self.failure.list_events(limit=20)
        checks = self.security.list_checks(limit=20)

        return {
            "labels": self.labels(),
            "posture": {**PAPER_POSTURE},
            "schema_version": SCHEMA_VERSION,
            "engine_version": ENGINE_VERSION,
            "terminal_verdict_target": TERMINAL_VERDICT,
            "llm_boundary": dict(LLM_BOUNDARY),
            "broker_registry": {
                "count": len(brokers),
                "brokers": brokers,
                "all_not_connected": all(
                    b["connection_status"] in ("NOT_CONNECTED", "SANDBOX_ONLY")
                    for b in brokers
                ),
            },
            "capability_viewer": {
                "count": len(caps),
                "capabilities": caps,
            },
            "sandbox_emulator": {
                "broker_id": SandboxEmulator.BROKER_ID,
                "valid_symbols": sorted(SandboxEmulator.VALID_SYMBOLS),
                "real_network": False,
                "executable": True,
                "note": "Only in-process emulator may simulate orders.",
            },
            "trust_center": {
                "pipelines": len(pipes),
                "open": sum(1 for p in pipes if p["status"] in ("DRAFT", "IN_PROGRESS")),
                "fully_approved_sandbox": sum(
                    1 for p in pipes if p["status"] == "FULLY_APPROVED_SANDBOX"
                ),
                "live_authorized_count": 0,
            },
            "approval_pipeline": {
                "required_stages": pipes[0]["required_stages"] if pipes else [
                    "OWNER", "SECURITY", "CREDENTIAL", "RISK", "ENVIRONMENT",
                    "SIMULATION", "PAPER_GRADUATION", "MANUAL_CONFIRMATION",
                ],
                "recent": pipes[:5],
            },
            "credential_metadata": {
                "references": len(creds),
                "all_unusable": all(not c["usable"] for c in creds) if creds else True,
                "all_no_secrets": all(not c["secret_material_present"] for c in creds) if creds else True,
                "items": creds[:20],
            },
            "recovery_center": {
                "events": len(failures),
                "recent": failures[:10],
            },
            "audit_timeline": {
                "events": len(audit),
                "recent": audit[:20],
            },
            "security_dashboard": {
                "checks": len(checks),
                "recent": checks[:10],
            },
            "abstraction": abstraction_surface(),
            "paper_only": True,
            "sandbox_only": True,
            "no_live_broker": True,
            "disclaimer": PAPER_POSTURE["disclaimer"],
        }
