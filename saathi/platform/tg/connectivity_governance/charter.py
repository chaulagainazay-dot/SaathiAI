"""M312 Connectivity Governance Charter."""
from __future__ import annotations

import json
import time
from typing import Any

from saathi.platform.tg.connectivity_governance.models import (
    AUTHORITY_VALUES,
    CHARTER_VERSION,
    GOVERNANCE_PRINCIPLES,
    MAX_STATE,
    PROHIBITED_OPERATIONS,
    SCHEMA_VERSION,
    TERMINAL_STATEMENTS,
    TERMINAL_VERDICT,
)


def build_charter() -> dict[str, Any]:
    return {
        "schema": "M312_CONNECTIVITY_GOVERNANCE_CHARTER",
        "charter_version": CHARTER_VERSION,
        "schema_version": SCHEMA_VERSION,
        "title": "Trading Connectivity Governance Charter",
        "purpose": (
            "Define who may request, approve, scope, expire, revoke and emergency-stop "
            "any future provider connectivity before any connection may be considered."
        ),
        "scope": {
            "in_scope": [
                "connectivity authority model",
                "provider governance registry",
                "approval and human authorization",
                "credential governance policy (references only)",
                "revocation and emergency shutdown",
                "incident response",
                "provider threat model",
                "maturity model",
                "evidence and certification",
            ],
            "out_of_scope": [
                "real provider connections",
                "credential storage or validation",
                "OAuth",
                "account access",
                "order submission",
                "canary activation",
                "live trading",
            ],
        },
        "governance_ownership": {
            "owner_role": "Connectivity Governance Owner (human)",
            "approver_role": "Connectivity Approver (human, maker-checker)",
            "operator_role": "Governance Operator (human)",
            "llm_role": "non-authoritative advisor only",
            "no_self_approval": True,
            "no_llm_approval": True,
        },
        "human_accountability": {
            "every_authority_expansion_requires_human_approval": True,
            "explicit_human_identity_required": True,
            "acknowledgements_required": True,
            "emergency_powers_require_human_actor": True,
            "llm_cannot_approve_or_activate": True,
        },
        "principles": list(GOVERNANCE_PRINCIPLES),
        "prohibited_operations": sorted(PROHIBITED_OPERATIONS),
        "approval_requirements": {
            "maker_checker": True,
            "mandatory_expiry": True,
            "narrow_scope": True,
            "provider_binding": True,
            "environment_binding": True,
            "approval_does_not_equal_activation": True,
            "no_self_approval": True,
            "no_llm_approval": True,
        },
        "revocation_rules": {
            "any_approval_revocable": True,
            "emergency_dominates": True,
            "revocation_is_durable": True,
            "recovery_requires_human_review": True,
        },
        "emergency_powers": {
            "override_all_approvals": True,
            "override_provider_eligibility": True,
            "override_credentials": True,
            "override_account_access": True,
            "override_execution_authority": True,
            "prevent_reconnection": True,
            "generate_durable_evidence": True,
        },
        "provider_admission_rules": {
            "no_connectivity_by_default": True,
            "documentation_review_required": True,
            "capability_allowlist_required": True,
            "domain_allowlist_required": True,
            "max_state_this_milestone": "MOCK_ELIGIBLE",
            "no_active_provider": True,
        },
        "evidence_requirements": {
            "every_decision_auditable": True,
            "evidence_hashing": True,
            "no_credentials_in_evidence": True,
        },
        "maturity_states": [
            "GOVERNANCE_NOT_ESTABLISHED",
            "GOVERNANCE_ONLY",
            "MOCK_CONTRACT_ELIGIBLE",
            "READ_ONLY_CANARY_ELIGIBLE",
            "EXTERNAL_PAPER_CANARY_ELIGIBLE",
            "LIVE_EXECUTION_PROHIBITED",
        ],
        "current_maturity": "GOVERNANCE_ONLY",
        "human_review_requirements": {
            "authority_expansion": True,
            "provider_admission": True,
            "canary_request": True,
            "incident_close": True,
            "emergency_recovery": True,
        },
        "implementation_boundaries": {
            "research_only": True,
            "paper_only": True,
            "sandbox_only": True,
            "offline_first": True,
            "no_real_provider_connection": True,
            "no_m320_auto_start": True,
        },
        "incident_obligations": {
            "detect_classify_contain_revoke": True,
            "preserve_evidence": True,
            "human_review_before_close": True,
        },
        "credential_restrictions": {
            "raw_credentials_forbidden": True,
            "no_chat_paste": True,
            "no_evidence_storage": True,
            "synthetic_references_only_this_milestone": True,
            "max_state": "REFERENCE_DECLARED",
        },
        "execution_restrictions": {
            "order_submission": False,
            "order_modification": False,
            "order_cancellation": False,
            "external_paper": False,
            "live_execution": False,
            "transfer": False,
            "withdrawal": False,
        },
        "production_restrictions": {
            "production_activation": False,
            "read_only_production": False,
            "live_trading": False,
        },
        "terminal_verdict_target": TERMINAL_VERDICT,
        "max_state": MAX_STATE,
        "statements": list(TERMINAL_STATEMENTS),
        "finalized": True,
        "immutable_when_finalized": True,
        **AUTHORITY_VALUES,
    }


def charter_public() -> dict[str, Any]:
    c = build_charter()
    c["as_of"] = time.time()
    return c
