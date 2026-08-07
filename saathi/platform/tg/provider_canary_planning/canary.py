"""M243 — Read-only canary architecture design.

State: CANARY_DESIGNED_NOT_AUTHORIZED
No runtime transport implementation.
"""
from __future__ import annotations

import json
import time
from typing import Any

from saathi.platform.tg.provider_canary_planning.models import (
    CANARY_DESIGN_STATE,
    PREFERRED_PROVIDER,
)
from saathi.platform.tg.provider_canary_planning.store import PlanningStore, _uid, evidence_hash

ARCHITECTURE = {
    "name": "read_only_provider_canary",
    "state": CANARY_DESIGN_STATE,
    "provider": PREFERRED_PROVIDER,
    "environment": "ONE_OWNER_CONTROLLED_ACCOUNT_ONE_ENV",
    "mode": "READ_ONLY",
    "activation": "MANUAL_ONLY",
    "revocation": "MANUAL_AND_KILL_SWITCH",
    "time_bounded": True,
    "rate_limited": True,
    "monitored": True,
    "fully_audited": True,
    "components": [
        "Owner Approval Center (existing)",
        "Credential Metadata Lifecycle (reference-only; no raw secrets to LLM)",
        "Transport Guard (endpoint + network allow-list)",
        "Canary Read Collector (future; not implemented)",
        "Snapshot Store (durable; no credentials)",
        "Reconciliation Engine (compare snapshots)",
        "Audit Evidence Store",
        "Monitoring & Abort Evaluator",
        "Kill Switch",
        "Operations Control Center UI (planning view)",
    ],
    "isolation": {
        "from_execution_systems": True,
        "from_order_submission": True,
        "from_portfolio_mutation": True,
        "from_trading_guardian_autonomous_actions": True,
        "from_llm_credential_path": True,
    },
    "trust_boundaries": [
        {
            "boundary": "owner_human",
            "description": "Only human owner may approve planning package and future activation.",
        },
        {
            "boundary": "credential_entry",
            "description": "Raw secret never enters LLM context; only reference IDs stored in SaathiOS.",
        },
        {
            "boundary": "network_allowlist",
            "description": "Only paper-api (or designated) host allowed; no OAuth login hosts.",
        },
        {
            "boundary": "endpoint_allowlist",
            "description": "Only GET account/positions/orders/activities families.",
        },
        {
            "boundary": "execution_isolation",
            "description": "No path into order placement, cancel, withdraw, transfer.",
        },
        {
            "boundary": "tg_autonomy_isolation",
            "description": "Trading Guardian cannot auto-act on canary data.",
        },
    ],
    "data_flow": [
        "owner_approved_credential_ref → transport_guard → allowed_GET → snapshot_normalize → durable_store → audit → recon → monitor",
    ],
    "storage_flow": [
        "snapshots + hashes + timestamps",
        "no raw credentials",
        "no full secret material",
        "retention-bounded purge job (future)",
    ],
    "audit_flow": [
        "every request attempt logged (url family, status, latency, hash of response redacted)",
        "abort events immutable",
        "revocation events immutable",
    ],
    "reconciliation_flow": [
        "baseline paper portfolio remains unchanged",
        "provider snapshot vs prior snapshot delta within tolerance",
        "unknown asset → abort",
    ],
    "kill_switch_flow": [
        "manual kill → stop collector → revoke local use of ref → optional external revoke runbook",
    ],
    "revocation_flow": [
        "owner revokes at provider console",
        "operator marks ref REVOKED",
        "transport refuses subsequent use",
        "external verification step in runbook",
    ],
    "error_flow": [
        "4xx auth → abort security",
        "429 → backoff then threshold abort",
        "5xx → warning then stop threshold",
        "schema unknown → manual review",
    ],
    "owner_approval_flow": [
        "M246 package review → APPROVE_PLANNING_PACKAGE_ONLY only",
        "separate future milestone required for any connectivity authority",
    ],
    "may_read": [
        "provider_identity", "account_metadata", "permissions", "balances",
        "positions", "order_history", "trade_history", "fee_history", "transaction_history",
    ],
    "must_not": [
        "order_placement", "order_cancellation", "order_modification",
        "withdrawal", "transfer", "account_administration", "sub_account_administration",
        "api_key_administration", "margin_activation", "leverage_activation",
    ],
    "network_allowlist_proposal": [
        "paper-api.alpaca.markets",  # preferred paper environment only
        # live api.alpaca.markets intentionally excluded from first canary proposal
    ],
    "endpoint_allowlist_proposal": [
        "GET /v2/clock",
        "GET /v2/account",
        "GET /v2/positions",
        "GET /v2/orders (read statuses only)",
        "GET /v2/account/portfolio/history",
        "GET /v2/account/activities",
        "GET /v2/assets",
    ],
    "endpoint_denylist_proposal": [
        "POST /v2/orders",
        "DELETE /v2/orders/*",
        "PATCH /v2/orders/*",
        "any withdrawal/transfer path",
        "any OAuth authorize path",
    ],
    "budgets": {
        "time_limit": "max 72 hours per canary window (proposal)",
        "call_budget": "max 500 authenticated GETs per window",
        "rate_limit_budget": "max 30 requests/minute; stop after 3 consecutive 429s",
        "retry_policy": "idempotent GET only; max 2 retries",
        "backoff_policy": "exponential 1s, 2s, 4s; no retry on 401/403",
        "data_retention_limit": "30 days for canary snapshots unless legal requires shorter",
    },
    "evidence_capture": [
        "request family + timestamp + response hash",
        "scope introspection result",
        "abort evidence packs",
    ],
    "rollback": [
        "disable collector",
        "revoke credential ref locally",
        "purge short-lived caches",
        "retain immutable audit",
        "paper portfolio and durable ledger remain authoritative and unchanged",
    ],
    "provider_adapter_implemented": False,
    "canary_activation_authorized": False,
}


class CanaryArchitecture:
    def __init__(self, store: PlanningStore):
        self.store = store

    def ensure_seeded(self) -> None:
        row = self.store.fetchone("SELECT COUNT(*) AS c FROM pcp_canary_plans")
        if row and int(row["c"]) > 0:
            return
        arch = ARCHITECTURE
        self.store.execute(
            """INSERT INTO pcp_canary_plans(
                id, provider, state, architecture_json, network_allowlist_json,
                endpoint_allowlist_json, budgets_json, evidence_hash, created_at
            ) VALUES(?,?,?,?,?,?,?,?,?)""",
            (
                _uid("can"), PREFERRED_PROVIDER, CANARY_DESIGN_STATE,
                json.dumps(arch),
                json.dumps(arch["network_allowlist_proposal"]),
                json.dumps(arch["endpoint_allowlist_proposal"]),
                json.dumps(arch["budgets"]),
                evidence_hash(arch),
                time.time(),
            ),
        )
        self.store.audit("canary.designed", subject=PREFERRED_PROVIDER, detail={"state": CANARY_DESIGN_STATE})

    def design(self) -> dict[str, Any]:
        self.ensure_seeded()
        row = self.store.fetchone("SELECT * FROM pcp_canary_plans ORDER BY created_at DESC LIMIT 1")
        assert row is not None
        arch = json.loads(row["architecture_json"] or "{}")
        return {
            **arch,
            "state": row["state"],
            "evidence_hash": row["evidence_hash"],
            "CANARY_ACTIVATION_AUTHORIZED": False,
            "REAL_CONNECTIVITY_AUTHORIZED": False,
        }

    def attempt_activate(self) -> dict[str, Any]:
        self.store.audit("canary.activate_refused", detail={"reason": "CANARY_ACTIVATION_AUTHORIZED=false"})
        return {
            "ok": False,
            "code": "CANARY_ACTIVATION_FORBIDDEN",
            "message": "Canary is designed but not authorized. Activation is forbidden in M240–M247.",
            "state": CANARY_DESIGN_STATE,
            "CANARY_ACTIVATION_AUTHORIZED": False,
            "REAL_CONNECTIVITY_AUTHORIZED": False,
        }
