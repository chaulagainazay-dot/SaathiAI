"""M247 — Provider Canary Planning Control Center read model."""
from __future__ import annotations

from typing import Any

from saathi.platform.tg.provider_canary_planning.models import (
    BOUNDARY_LABELS,
    ENGINE_VERSION,
    FALLBACK_PROVIDER,
    PCP_POSTURE,
    PREFERRED_PROVIDER,
    SCHEMA_VERSION,
    TERMINAL_VERDICT,
)


class PlanningControlCenter:
    def __init__(self, service: Any):
        self.svc = service

    def labels(self) -> dict[str, str]:
        return dict(BOUNDARY_LABELS)

    def overview(self) -> dict[str, Any]:
        return {
            "labels": self.labels(),
            "posture": dict(PCP_POSTURE),
            "schema_version": SCHEMA_VERSION,
            "engine_version": ENGINE_VERSION,
            "terminal_verdict_target": TERMINAL_VERDICT,
            "preferred_provider": PREFERRED_PROVIDER,
            "fallback_provider": FALLBACK_PROVIDER,
            "sections": {
                "planning_overview": {"via": "GET /dashboard"},
                "candidate_ranking": {"via": "GET /rankings"},
                "preferred_provider": {"via": "GET /preferred"},
                "fallback_provider": {"via": "GET /fallback"},
                "evidence_sources": {"via": "GET /sources"},
                "capability_map": {"via": "GET /capabilities"},
                "endpoint_classification": {"via": "GET /endpoints"},
                "eligibility_review": {"via": "GET /eligibility"},
                "terms_and_data_governance": {"via": "GET /terms"},
                "proposed_read_only_scopes": {"via": "GET /scopes"},
                "forbidden_scopes": {"via": "GET /scopes"},
                "canary_architecture": {"via": "GET /canary"},
                "credential_ceremony": {"via": "GET /credential-ceremony"},
                "network_policy": {"via": "GET /network-policy"},
                "monitoring_plan": {"via": "GET /monitoring"},
                "reconciliation_plan": {"via": "GET /reconciliation"},
                "acceptance_criteria": {"via": "GET /acceptance"},
                "abort_triggers": {"via": "GET /abort"},
                "revocation_plan": {"via": "GET /credential-ceremony"},
                "human_approval_package": {"via": "GET /owner-package"},
                "missing_evidence": {"via": "eligibility.unresolved"},
                "certification": {"via": "POST /certify"},
                "evidence_centre": {"path": "docs/trading/m240_m247_evidence/"},
            },
            "ui_constraints": {
                "accept_credentials": False,
                "open_oauth": False,
                "open_provider_login": False,
                "connect_provider": False,
                "call_private_apis": False,
                "activate_canary": False,
                "approve_legal_review": False,
                "generate_owner_signoff": False,
                "authorise_connectivity": False,
                "enable_live_trading": False,
            },
            "REAL_CONNECTIVITY_AUTHORIZED": False,
            "CREDENTIAL_PROVISIONING_AUTHORIZED": False,
            "CANARY_ACTIVATION_AUTHORIZED": False,
            "LIVE_TRADING_AUTHORIZED": False,
            "disclaimer": PCP_POSTURE["disclaimer"],
        }
