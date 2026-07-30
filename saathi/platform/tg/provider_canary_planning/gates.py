"""M245 — Canary acceptance, monitoring and abort criteria."""
from __future__ import annotations

import json
import time
from typing import Any

from saathi.platform.tg.provider_canary_planning.models import PREFERRED_PROVIDER
from saathi.platform.tg.provider_canary_planning.store import PlanningStore, _uid, evidence_hash

PRE_ACTIVATION = [
    "owner_approval",
    "security_approval",
    "legal_and_eligibility_review",
    "exact_read_only_scope_match",
    "provider_identity_verification",
    "network_allow_list_verification",
    "endpoint_allow_list_verification",
    "credential_expiry_configured",
    "revocation_path_verified",
    "kill_switch_verified",
    "audit_storage_verified",
    "reconciliation_baseline_ready",
    "monitoring_ready",
    "incident_owner_assigned",
    "rollback_documented",
]

SUCCESS = [
    "only_approved_endpoints_used",
    "only_approved_read_scopes_observed",
    "no_provider_identity_mismatch",
    "no_secret_leakage",
    "no_write_capability",
    "no_order_path",
    "no_withdrawal_path",
    "snapshots_within_expected_timing",
    "reconciliation_within_tolerance",
    "rate_limits_respected",
    "audit_trail_complete",
    "expiry_works",
    "revocation_works",
    "disconnect_works",
    "paper_portfolio_unchanged",
    "durable_ledger_consistent",
    "no_trading_guardian_execution_authority_introduced",
]

ABORT_TRIGGERS = [
    "unexpected_write_scope",
    "mixed_read_write_scope",
    "withdrawal_permission",
    "transfer_permission",
    "provider_mismatch",
    "account_mismatch",
    "credential_leak",
    "suspicious_logging",
    "network_destination_mismatch",
    "endpoint_outside_allow_list",
    "scope_drift",
    "account_permission_mutation",
    "reconciliation_failure",
    "unknown_asset",
    "unexplained_balance_discrepancy",
    "stale_data_beyond_threshold",
    "replayed_response",
    "audit_failure",
    "revocation_failure",
    "kill_switch_failure",
    "repeated_rate_limit_violation",
    "provider_suspension",
    "legal_or_eligibility_concern",
    "owner_withdrawal_of_approval",
    "security_withdrawal_of_approval",
]

THRESHOLDS = {
    "warning": {
        "stale_data_seconds": 900,
        "single_429": 1,
        "recon_delta_bps": 50,
    },
    "stop": {
        "stale_data_seconds": 3600,
        "consecutive_429": 3,
        "recon_delta_bps": 200,
        "auth_failures": 1,
    },
    "manual_review": {
        "unknown_schema_fields": 1,
        "unknown_asset": 1,
        "pagination_gap": 1,
    },
    "security_abort_no_auto_recovery": True,
    "recovery_procedure": "Human-only re-entry after full incident review; no automated recovery after security abort.",
    "re_entry_requirements": [
        "incident closed",
        "credential rotated or destroyed",
        "fresh owner + security approval",
        "gates re-validated",
        "new planning/authority milestone if connectivity still not authorized",
    ],
}

MONITORING_PLAN = {
    "signals": [
        "request_count", "error_rate", "latency", "rate_limit_headers",
        "scope_introspection", "endpoint_allowlist_hits", "denylist_blocks",
        "snapshot_freshness", "recon_delta", "kill_switch_state",
    ],
    "alerting": "operator + owner on stop/security abort",
    "dashboard": "/trading/provider-canary-planning (planning view only in M247)",
}

RECONCILIATION_PLAN = {
    "baseline": "paper portfolio and durable ledger remain source of truth for trading",
    "compare": "provider snapshot series for continuity only",
    "tolerance": "threshold-defined; unknown assets fail closed",
    "does_not_mutate": ["paper_portfolio", "orders", "positions_execution_path"],
}


class CanaryGates:
    def __init__(self, store: PlanningStore):
        self.store = store

    def ensure_seeded(self) -> None:
        row = self.store.fetchone("SELECT COUNT(*) AS c FROM pcp_gates")
        if row and int(row["c"]) > 0:
            return
        payload = {
            "pre_activation": PRE_ACTIVATION,
            "success": SUCCESS,
            "abort": ABORT_TRIGGERS,
            "thresholds": THRESHOLDS,
            "monitoring": MONITORING_PLAN,
            "reconciliation": RECONCILIATION_PLAN,
        }
        self.store.execute(
            """INSERT INTO pcp_gates(
                id, provider, pre_activation_json, success_json, abort_json,
                thresholds_json, evidence_hash, created_at
            ) VALUES(?,?,?,?,?,?,?,?)""",
            (
                _uid("gate"), PREFERRED_PROVIDER,
                json.dumps(PRE_ACTIVATION),
                json.dumps(SUCCESS),
                json.dumps(ABORT_TRIGGERS),
                json.dumps(THRESHOLDS),
                evidence_hash(payload),
                time.time(),
            ),
        )
        self.store.audit("gates.seeded", subject=PREFERRED_PROVIDER)

    def gates(self) -> dict[str, Any]:
        self.ensure_seeded()
        row = self.store.fetchone("SELECT * FROM pcp_gates ORDER BY created_at DESC LIMIT 1")
        assert row is not None
        return {
            "provider": row["provider"],
            "pre_activation_gates": json.loads(row["pre_activation_json"] or "[]"),
            "success_criteria": json.loads(row["success_json"] or "[]"),
            "abort_triggers": json.loads(row["abort_json"] or "[]"),
            "thresholds": json.loads(row["thresholds_json"] or "{}"),
            "monitoring_plan": MONITORING_PLAN,
            "reconciliation_plan": RECONCILIATION_PLAN,
            "automated_recovery_after_security_abort": False,
            "CANARY_ACTIVATION_AUTHORIZED": False,
            "REAL_CONNECTIVITY_AUTHORIZED": False,
            "evidence_hash": row["evidence_hash"],
        }
