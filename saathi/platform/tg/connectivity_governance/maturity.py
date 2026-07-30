"""Connectivity maturity model — remains GOVERNANCE_ONLY."""
from __future__ import annotations

from typing import Any

from saathi.platform.tg.connectivity_governance.models import (
    AUTHORITY_VALUES,
    CURRENT_MATURITY,
    MaturityLevel,
)

MATURITY_DEFINITIONS = {
    MaturityLevel.GOVERNANCE_NOT_ESTABLISHED.value: {
        "level": 0,
        "requirements": [],
        "description": "No governance charter or authority model",
    },
    MaturityLevel.GOVERNANCE_ONLY.value: {
        "level": 1,
        "requirements": [
            "charter", "authority_model", "provider_registry", "approval_framework",
            "credential_policy", "threat_model", "incident_response", "certification",
        ],
        "description": "Governance complete; no provider connection",
    },
    MaturityLevel.MOCK_CONTRACT_ELIGIBLE.value: {
        "level": 2,
        "requirements": [
            "governance_complete", "mock_provider_contracts", "no_real_credential",
            "no_network_provider_connection",
        ],
        "description": "Future-only — mock contracts",
        "future_only": True,
    },
    MaturityLevel.READ_ONLY_CANARY_ELIGIBLE.value: {
        "level": 3,
        "requirements": [
            "human_authorization", "approved_provider", "approved_jurisdiction",
            "read_only_capability_scope", "disposable_credential_reference",
            "automatic_expiry", "revocation_drill", "incident_readiness",
        ],
        "description": "Future-only — read-only canary",
        "future_only": True,
    },
    MaturityLevel.EXTERNAL_PAPER_CANARY_ELIGIBLE.value: {
        "level": 4,
        "requirements": [
            "successful_read_only_canary", "separate_human_authorization",
            "paper_environment_proof", "bounded_notional", "execution_kill_switch",
            "reconciliation", "no_live_trading",
        ],
        "description": "Future-only — external paper canary",
        "future_only": True,
    },
    MaturityLevel.LIVE_EXECUTION_PROHIBITED.value: {
        "level": 5,
        "requirements": ["live_execution_remains_prohibited"],
        "description": "Live execution has no automatic unlock path",
        "no_automatic_unlock": True,
    },
}


def maturity_status(*, checks: dict[str, bool] | None = None) -> dict[str, Any]:
    checks = checks or {}
    gov_reqs = MATURITY_DEFINITIONS[MaturityLevel.GOVERNANCE_ONLY.value]["requirements"]
    satisfied = {r: checks.get(r, True) for r in gov_reqs}  # default true when service bootstrapped
    all_gov = all(satisfied.values())
    current = CURRENT_MATURITY if all_gov else MaturityLevel.GOVERNANCE_NOT_ESTABLISHED.value
    return {
        "ok": True,
        "current": current,
        "current_level": 1 if current == CURRENT_MATURITY else 0,
        "definitions": MATURITY_DEFINITIONS,
        "governance_requirements": satisfied,
        "can_advance_automatically": False,
        "live_execution_unlock_path": False,
        "max_this_milestone": CURRENT_MATURITY,
        **AUTHORITY_VALUES,
    }
