"""M231 — Read-Only Readiness Control Center read model."""
from __future__ import annotations

from typing import Any

from saathi.platform.tg.broker_readiness.models import (
    ENGINE_VERSION,
    LLM_BOUNDARY,
    READINESS_POSTURE,
    SCHEMA_VERSION,
    TERMINAL_VERDICT,
)


class ReadinessControlCenter:
    def __init__(self, service: Any):
        self.svc = service

    def labels(self) -> dict[str, str]:
        return {
            "simulation_only": "SIMULATION ONLY",
            "no_real_connection": "NO REAL CONNECTION",
            "no_real_credential": "NO REAL CREDENTIAL",
            "read_only_architecture": "READ-ONLY ARCHITECTURE",
            "no_order_submission": "NO ORDER SUBMISSION",
            "live_trading_not_authorized": "LIVE TRADING NOT AUTHORIZED",
            "paper_only": "PAPER ONLY",
            "sandbox_only": "SANDBOX ONLY",
        }

    def overview(self) -> dict[str, Any]:
        providers = self.svc.list_providers()
        adapters = self.svc.adapter_contract()
        creds = self.svc.list_credentials()
        sessions = self.svc.list_sessions()
        snaps = self.svc.list_snapshots()
        recon = self.svc.list_reconciliations()
        drills = self.svc.list_drills()
        audit = self.svc.audit_timeline(limit=30)
        return {
            "labels": self.labels(),
            "posture": {**READINESS_POSTURE},
            "schema_version": SCHEMA_VERSION,
            "engine_version": ENGINE_VERSION,
            "terminal_verdict_target": TERMINAL_VERDICT,
            "llm_boundary": dict(LLM_BOUNDARY),
            "readiness_overview": {
                "providers": providers.get("providers", []),
                "connection_default": "SIMULATED_NOT_CONNECTED",
            },
            "provider_adapter_contracts": adapters,
            "capability_policy": {"engine": "M225", "write_rejected": True},
            "credential_lifecycle": {
                "count": len(creds.get("credentials", [])),
                "all_unusable_for_real": all(
                    not c.get("credential_usable_for_real_connection")
                    for c in creds.get("credentials", [])
                ) if creds.get("credentials") else True,
                "items": creds.get("credentials", [])[:20],
            },
            "scope_validator": {"milestone": "M227", "least_privilege": True},
            "connection_state": {
                "sessions": sessions.get("sessions", [])[:20],
                "count": len(sessions.get("sessions", [])),
            },
            "account_snapshot_viewer": {
                "snapshots": snaps.get("snapshots", [])[:10],
                "count": len(snaps.get("snapshots", [])),
            },
            "reconciliation_center": {
                "results": recon.get("results", [])[:10],
            },
            "revocation_center": {"drills": [d for d in drills.get("drills", []) if "revoc" in d.get("scenario", "")][:10]},
            "expiry_center": {"drills": [d for d in drills.get("drills", []) if "expir" in d.get("scenario", "")][:10]},
            "incident_drills": drills,
            "audit_timeline": audit,
            "security_results": {"run_via": "POST /security/scan"},
            "evidence_center": {"path": "docs/trading/m224_m231_evidence/"},
            "readiness_certification": {
                "verdict_target": TERMINAL_VERDICT,
                "owner_signoff": "NOT_CLAIMED_AUTOMATED_ONLY",
                "production_read_only_authority": False,
            },
            "ui_constraints": {
                "accepts_raw_secrets": False,
                "real_connection_button": False,
                "enable_trading_button": False,
                "converts_to_real_authority": False,
            },
            "simulation_only": True,
            "disclaimer": READINESS_POSTURE["disclaimer"],
        }
