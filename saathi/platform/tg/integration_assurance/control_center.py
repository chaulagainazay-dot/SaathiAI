"""M239 — Reproducibility and Authorization Control Center read model."""
from __future__ import annotations

from typing import Any

from saathi.platform.tg.integration_assurance.models import (
    BOUNDARY_LABELS,
    ENGINE_VERSION,
    IA_POSTURE,
    LLM_BOUNDARY,
    SCHEMA_VERSION,
    TERMINAL_VERDICT,
)


class AssuranceControlCenter:
    def __init__(self, service: Any):
        self.svc = service

    def labels(self) -> dict[str, str]:
        return dict(BOUNDARY_LABELS)

    def overview(self) -> dict[str, Any]:
        return {
            "labels": self.labels(),
            "posture": dict(IA_POSTURE),
            "schema_version": SCHEMA_VERSION,
            "engine_version": ENGINE_VERSION,
            "terminal_verdict_target": TERMINAL_VERDICT,
            "llm_boundary": dict(LLM_BOUNDARY),
            "sections": {
                "reproducibility_overview": {"via": "source_audit + reproduction"},
                "clean_clone_status": {"via": "GET /reproduction/clean-clone"},
                "required_source_audit": {"via": "GET /source-audit"},
                "hidden_dependency_findings": {"via": "source_audit items"},
                "environment_contract": {"via": "GET /environment"},
                "dependency_inventory": {"via": "GET /dependencies"},
                "lockfile_status": {"via": "GET /lockfiles"},
                "sbom_viewer": {"via": "GET /sbom"},
                "provenance_viewer": {"via": "GET /provenance"},
                "supply_chain_risks": {"via": "GET /supply-chain"},
                "assurance_gates": {"via": "GET /assurance-gates"},
                "authorization_planning": {"via": "GET /authorization/plan"},
                "approval_domains": {"via": "GET /authorization/domains"},
                "read_only_eligibility": {"via": "GET /authorization/eligibility"},
                "network_policy": {"via": "GET /network-policy"},
                "evidence_center": {"path": "docs/trading/m232_m239_evidence/"},
                "certification_summary": {"via": "GET /verdict + POST /certify"},
            },
            "ui_constraints": {
                "upload_credentials": False,
                "accept_secrets": False,
                "open_provider_login": False,
                "initiate_oauth": False,
                "activate_provider": False,
                "approve_owner_authorization": False,
                "approve_security_authorization": False,
                "enable_external_transport": False,
                "create_production_connectivity": False,
            },
            "REAL_CONNECTIVITY_AUTHORIZED": False,
            "disclaimer": IA_POSTURE["disclaimer"],
        }
