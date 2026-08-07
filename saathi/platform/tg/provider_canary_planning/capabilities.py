"""M241 — Provider-specific capability and endpoint map for preferred provider.

provider_adapter_implemented = false always.
No runtime calls. No SDK code embedded for execution.
"""
from __future__ import annotations

import json
import time
from typing import Any

from saathi.platform.tg.provider_canary_planning.models import (
    PREFERRED_PROVIDER,
    PROVIDER_ADAPTER_IMPLEMENTED,
    AuthCategory,
    RETRIEVAL_DATE,
)
from saathi.platform.tg.provider_canary_planning.store import PlanningStore, _uid, evidence_hash

# Endpoint families for Alpaca Trading API (preferred). Methods/scopes are planning notes
# derived from official docs research — not implemented adapters.
ALPACA_ENDPOINTS: list[dict[str, Any]] = [
    {
        "endpoint_family": "server_time",
        "method": "GET",
        "path_pattern": "/v2/clock",
        "auth_category": AuthCategory.PRIVATE_READ_ONLY.value,
        "required_scope": "account_read",
        "pagination": "none",
        "rate_limit": "provider standard; canary budget applies",
        "timestamp_behaviour": "ISO8601 market clock timestamps",
        "schema_notes": "is_open, next_open, next_close",
        "retention_limits": "n/a (point-in-time)",
        "error_behaviour": "401/403 on bad/missing key",
        "canary_relevance": "high — health/clock sanity",
        "allowed_or_forbidden": "ALLOWED_PROPOSED",
        "source_evidence": "https://docs.alpaca.markets/docs/getting-started-with-trading-api",
    },
    {
        "endpoint_family": "provider_health",
        "method": "GET",
        "path_pattern": "/v2/clock",
        "auth_category": AuthCategory.PRIVATE_READ_ONLY.value,
        "required_scope": "account_read",
        "pagination": "none",
        "rate_limit": "provider standard",
        "timestamp_behaviour": "ISO8601",
        "schema_notes": "reuse clock as readiness signal",
        "retention_limits": "n/a",
        "error_behaviour": "5xx → abort threshold",
        "canary_relevance": "high",
        "allowed_or_forbidden": "ALLOWED_PROPOSED",
        "source_evidence": "https://docs.alpaca.markets/docs/getting-started-with-trading-api",
    },
    {
        "endpoint_family": "account_metadata",
        "method": "GET",
        "path_pattern": "/v2/account",
        "auth_category": AuthCategory.PRIVATE_READ_ONLY.value,
        "required_scope": "account_read",
        "pagination": "none",
        "rate_limit": "provider standard",
        "timestamp_behaviour": "created_at timestamps",
        "schema_notes": "account status, currency, buying_power (read); do not act on trading fields",
        "retention_limits": "store metadata only within retention plan",
        "error_behaviour": "403 if key lacks account access",
        "canary_relevance": "high — identity and status",
        "allowed_or_forbidden": "ALLOWED_PROPOSED",
        "source_evidence": "https://docs.alpaca.markets/docs/getting-started-with-trading-api",
    },
    {
        "endpoint_family": "account_permissions",
        "method": "GET",
        "path_pattern": "/v2/account (status + configs as available)",
        "auth_category": AuthCategory.PRIVATE_READ_ONLY.value,
        "required_scope": "account_read",
        "pagination": "none",
        "rate_limit": "provider standard",
        "timestamp_behaviour": "n/a",
        "schema_notes": "Infer trading-blocked flags; abort if unexpected write-capable status",
        "retention_limits": "audit only",
        "error_behaviour": "missing fields → UNRESOLVED",
        "canary_relevance": "critical — scope drift detection",
        "allowed_or_forbidden": "ALLOWED_PROPOSED",
        "source_evidence": "https://docs.alpaca.markets/docs/getting-started-with-trading-api",
    },
    {
        "endpoint_family": "balances",
        "method": "GET",
        "path_pattern": "/v2/account",
        "auth_category": AuthCategory.PRIVATE_READ_ONLY.value,
        "required_scope": "account_read",
        "pagination": "none",
        "rate_limit": "provider standard",
        "timestamp_behaviour": "point-in-time",
        "schema_notes": "cash, equity, portfolio_value fields",
        "retention_limits": "canary retention window",
        "error_behaviour": "4xx abort review",
        "canary_relevance": "high",
        "allowed_or_forbidden": "ALLOWED_PROPOSED",
        "source_evidence": "https://docs.alpaca.markets/docs/getting-started-with-trading-api",
    },
    {
        "endpoint_family": "positions",
        "method": "GET",
        "path_pattern": "/v2/positions",
        "auth_category": AuthCategory.PRIVATE_READ_ONLY.value,
        "required_scope": "account_read",
        "pagination": "none (list)",
        "rate_limit": "provider standard",
        "timestamp_behaviour": "mark-to-market timestamps if present",
        "schema_notes": "symbol, qty, market_value, avg_entry",
        "retention_limits": "canary retention",
        "error_behaviour": "empty list ok",
        "canary_relevance": "high",
        "allowed_or_forbidden": "ALLOWED_PROPOSED",
        "source_evidence": "https://docs.alpaca.markets/docs/getting-started-with-trading-api",
    },
    {
        "endpoint_family": "portfolio",
        "method": "GET",
        "path_pattern": "/v2/account/portfolio/history",
        "auth_category": AuthCategory.PRIVATE_READ_ONLY.value,
        "required_scope": "account_read",
        "pagination": "period/timeframe params",
        "rate_limit": "provider standard",
        "timestamp_behaviour": "timestamp arrays",
        "schema_notes": "equity/history series",
        "retention_limits": "bounded series only",
        "error_behaviour": "400 on bad params",
        "canary_relevance": "medium",
        "allowed_or_forbidden": "ALLOWED_PROPOSED",
        "source_evidence": "https://docs.alpaca.markets/docs/getting-started-with-trading-api",
    },
    {
        "endpoint_family": "open_order_observation",
        "method": "GET",
        "path_pattern": "/v2/orders?status=open",
        "auth_category": AuthCategory.PRIVATE_READ_ONLY.value,
        "required_scope": "account_read",
        "pagination": "limit + until/after",
        "rate_limit": "provider standard",
        "timestamp_behaviour": "submitted_at, filled_at",
        "schema_notes": "read-only observation of open orders",
        "retention_limits": "canary retention",
        "error_behaviour": "empty ok",
        "canary_relevance": "high",
        "allowed_or_forbidden": "ALLOWED_PROPOSED",
        "source_evidence": "https://docs.alpaca.markets/docs/getting-started-with-trading-api",
    },
    {
        "endpoint_family": "order_history",
        "method": "GET",
        "path_pattern": "/v2/orders?status=all|closed",
        "auth_category": AuthCategory.PRIVATE_READ_ONLY.value,
        "required_scope": "account_read",
        "pagination": "limit + direction",
        "rate_limit": "provider standard",
        "timestamp_behaviour": "ISO timestamps",
        "schema_notes": "historical orders read-only",
        "retention_limits": "provider history window + local retention plan",
        "error_behaviour": "pagination must be complete",
        "canary_relevance": "high",
        "allowed_or_forbidden": "ALLOWED_PROPOSED",
        "source_evidence": "https://docs.alpaca.markets/docs/getting-started-with-trading-api",
    },
    {
        "endpoint_family": "trade_history",
        "method": "GET",
        "path_pattern": "/v2/account/activities/FILL",
        "auth_category": AuthCategory.PRIVATE_READ_ONLY.value,
        "required_scope": "account_read",
        "pagination": "page_token",
        "rate_limit": "provider standard",
        "timestamp_behaviour": "transaction_time",
        "schema_notes": "fills/activity feed",
        "retention_limits": "bounded window",
        "error_behaviour": "incomplete page → abort",
        "canary_relevance": "high",
        "allowed_or_forbidden": "ALLOWED_PROPOSED",
        "source_evidence": "https://docs.alpaca.markets/docs/getting-started-with-trading-api",
    },
    {
        "endpoint_family": "transactions",
        "method": "GET",
        "path_pattern": "/v2/account/activities",
        "auth_category": AuthCategory.PRIVATE_READ_ONLY.value,
        "required_scope": "account_read",
        "pagination": "page_token",
        "rate_limit": "provider standard",
        "timestamp_behaviour": "transaction_time",
        "schema_notes": "non-trading activity types may appear; filter carefully",
        "retention_limits": "bounded",
        "error_behaviour": "unknown activity types → review",
        "canary_relevance": "medium",
        "allowed_or_forbidden": "ALLOWED_PROPOSED",
        "source_evidence": "https://docs.alpaca.markets/docs/getting-started-with-trading-api",
    },
    {
        "endpoint_family": "deposits",
        "method": "GET",
        "path_pattern": "/v2/account/activities (CSD/JNLC etc. as applicable)",
        "auth_category": AuthCategory.PRIVATE_READ_ONLY.value,
        "required_scope": "account_read",
        "pagination": "page_token",
        "rate_limit": "provider standard",
        "timestamp_behaviour": "transaction_time",
        "schema_notes": "observe only; never initiate deposit",
        "retention_limits": "bounded",
        "error_behaviour": "n/a",
        "canary_relevance": "low",
        "allowed_or_forbidden": "ALLOWED_PROPOSED",
        "source_evidence": "https://docs.alpaca.markets/docs/getting-started-with-trading-api",
    },
    {
        "endpoint_family": "withdrawals",
        "method": "ANY",
        "path_pattern": "withdrawal/transfer write endpoints",
        "auth_category": AuthCategory.WITHDRAWAL_WRITE.value,
        "required_scope": "FORBIDDEN",
        "pagination": "n/a",
        "rate_limit": "n/a",
        "timestamp_behaviour": "n/a",
        "schema_notes": "Any withdrawal capability is forbidden",
        "retention_limits": "n/a",
        "error_behaviour": "must never be callable",
        "canary_relevance": "abort if present",
        "allowed_or_forbidden": "FORBIDDEN",
        "source_evidence": "planning invariant",
    },
    {
        "endpoint_family": "transfers",
        "method": "ANY",
        "path_pattern": "transfer write endpoints",
        "auth_category": AuthCategory.TRANSFER_WRITE.value,
        "required_scope": "FORBIDDEN",
        "pagination": "n/a",
        "rate_limit": "n/a",
        "timestamp_behaviour": "n/a",
        "schema_notes": "Transfer initiation forbidden",
        "retention_limits": "n/a",
        "error_behaviour": "must never be callable",
        "canary_relevance": "abort if present",
        "allowed_or_forbidden": "FORBIDDEN",
        "source_evidence": "planning invariant",
    },
    {
        "endpoint_family": "fees",
        "method": "GET",
        "path_pattern": "/v2/account/activities (FEE/CINT etc.)",
        "auth_category": AuthCategory.PRIVATE_READ_ONLY.value,
        "required_scope": "account_read",
        "pagination": "page_token",
        "rate_limit": "provider standard",
        "timestamp_behaviour": "transaction_time",
        "schema_notes": "fee history observation",
        "retention_limits": "bounded",
        "error_behaviour": "n/a",
        "canary_relevance": "medium",
        "allowed_or_forbidden": "ALLOWED_PROPOSED",
        "source_evidence": "https://docs.alpaca.markets/docs/getting-started-with-trading-api",
    },
    {
        "endpoint_family": "margin_metadata",
        "method": "GET",
        "path_pattern": "/v2/account (margin fields if present)",
        "auth_category": AuthCategory.PRIVATE_READ_ONLY.value,
        "required_scope": "account_read",
        "pagination": "none",
        "rate_limit": "provider standard",
        "timestamp_behaviour": "point-in-time",
        "schema_notes": "read margin metadata only; never activate margin/leverage",
        "retention_limits": "audit",
        "error_behaviour": "n/a",
        "canary_relevance": "low",
        "allowed_or_forbidden": "ALLOWED_PROPOSED",
        "source_evidence": "https://docs.alpaca.markets/docs/getting-started-with-trading-api",
    },
    {
        "endpoint_family": "asset_metadata",
        "method": "GET",
        "path_pattern": "/v2/assets",
        "auth_category": AuthCategory.PRIVATE_READ_ONLY.value,
        "required_scope": "account_read",
        "pagination": "query filters",
        "rate_limit": "provider standard",
        "timestamp_behaviour": "n/a",
        "schema_notes": "tradable asset catalog",
        "retention_limits": "reference data retention",
        "error_behaviour": "n/a",
        "canary_relevance": "medium",
        "allowed_or_forbidden": "ALLOWED_PROPOSED",
        "source_evidence": "https://docs.alpaca.markets/docs/getting-started-with-trading-api",
    },
    {
        "endpoint_family": "rate_limit_status",
        "method": "RESPONSE_HEADERS",
        "path_pattern": "any allowed GET",
        "auth_category": AuthCategory.PRIVATE_READ_ONLY.value,
        "required_scope": "account_read",
        "pagination": "n/a",
        "rate_limit": "observe X-RateLimit-* or equivalent if present",
        "timestamp_behaviour": "n/a",
        "schema_notes": "monitor remaining budget",
        "retention_limits": "audit",
        "error_behaviour": "429 → backoff then abort threshold",
        "canary_relevance": "high",
        "allowed_or_forbidden": "ALLOWED_PROPOSED",
        "source_evidence": "provider rate-limit behaviour (verify at canary time)",
    },
    {
        "endpoint_family": "order_placement",
        "method": "POST",
        "path_pattern": "/v2/orders",
        "auth_category": AuthCategory.TRADING_WRITE.value,
        "required_scope": "FORBIDDEN",
        "pagination": "n/a",
        "rate_limit": "n/a",
        "timestamp_behaviour": "n/a",
        "schema_notes": "Order submission forbidden",
        "retention_limits": "n/a",
        "error_behaviour": "must be blocked by allow-list and credential scope",
        "canary_relevance": "abort if reachable",
        "allowed_or_forbidden": "FORBIDDEN",
        "source_evidence": "planning invariant",
    },
    {
        "endpoint_family": "order_cancellation",
        "method": "DELETE",
        "path_pattern": "/v2/orders/{id}",
        "auth_category": AuthCategory.TRADING_WRITE.value,
        "required_scope": "FORBIDDEN",
        "pagination": "n/a",
        "rate_limit": "n/a",
        "timestamp_behaviour": "n/a",
        "schema_notes": "Order cancel forbidden",
        "retention_limits": "n/a",
        "error_behaviour": "must be blocked",
        "canary_relevance": "abort if reachable",
        "allowed_or_forbidden": "FORBIDDEN",
        "source_evidence": "planning invariant",
    },
    {
        "endpoint_family": "order_modification",
        "method": "PATCH",
        "path_pattern": "/v2/orders/{id}",
        "auth_category": AuthCategory.TRADING_WRITE.value,
        "required_scope": "FORBIDDEN",
        "pagination": "n/a",
        "rate_limit": "n/a",
        "timestamp_behaviour": "n/a",
        "schema_notes": "Order modify forbidden",
        "retention_limits": "n/a",
        "error_behaviour": "must be blocked",
        "canary_relevance": "abort if reachable",
        "allowed_or_forbidden": "FORBIDDEN",
        "source_evidence": "planning invariant",
    },
    {
        "endpoint_family": "public_market_data",
        "method": "GET",
        "path_pattern": "data.alpaca.markets public/SIP feeds (optional)",
        "auth_category": AuthCategory.PUBLIC_UNAUTHENTICATED.value,
        "required_scope": "none_or_market_data_key",
        "pagination": "varies",
        "rate_limit": "market data plan limits",
        "timestamp_behaviour": "exchange timestamps",
        "schema_notes": "Optional; not required for account canary; redistribution restricted",
        "retention_limits": "data licence limits",
        "error_behaviour": "n/a",
        "canary_relevance": "out of scope for first account canary",
        "allowed_or_forbidden": "OUT_OF_SCOPE",
        "source_evidence": "https://docs.alpaca.markets/docs/getting-started-with-alpaca-market-data",
    },
]

PROPOSED_READ_ONLY_SCOPES = [
    {
        "scope_name": "account_read",
        "kind": "PROPOSED_READ_ONLY",
        "rationale": "Minimum scope to read account metadata, balances, positions, and history.",
        "source_evidence": "Alpaca Trading API account/positions/orders GET families",
    },
    {
        "scope_name": "orders_read",
        "kind": "PROPOSED_READ_ONLY",
        "rationale": "Read open and historical orders only; never place/cancel/modify.",
        "source_evidence": "GET /v2/orders",
    },
    {
        "scope_name": "activities_read",
        "kind": "PROPOSED_READ_ONLY",
        "rationale": "Read fills, fees, and transaction history.",
        "source_evidence": "GET /v2/account/activities",
    },
]

FORBIDDEN_SCOPES = [
    {
        "scope_name": "trading_write",
        "kind": "FORBIDDEN",
        "rationale": "Any order place/cancel/modify permission.",
        "source_evidence": "planning invariant",
    },
    {
        "scope_name": "withdrawal",
        "kind": "FORBIDDEN",
        "rationale": "Withdrawal capability must never be granted.",
        "source_evidence": "planning invariant",
    },
    {
        "scope_name": "transfer",
        "kind": "FORBIDDEN",
        "rationale": "Transfer initiation forbidden.",
        "source_evidence": "planning invariant",
    },
    {
        "scope_name": "account_admin",
        "kind": "FORBIDDEN",
        "rationale": "Account/sub-account administration forbidden.",
        "source_evidence": "planning invariant",
    },
    {
        "scope_name": "credential_admin",
        "kind": "FORBIDDEN",
        "rationale": "API-key administration from SaathiOS forbidden.",
        "source_evidence": "planning invariant",
    },
    {
        "scope_name": "margin_activation",
        "kind": "FORBIDDEN",
        "rationale": "Margin/leverage activation forbidden.",
        "source_evidence": "planning invariant",
    },
    {
        "scope_name": "oauth_full_access",
        "kind": "FORBIDDEN",
        "rationale": "OAuth sessions out of scope and forbidden for this canary design.",
        "source_evidence": "planning invariant",
    },
]


class CapabilityMap:
    def __init__(self, store: PlanningStore):
        self.store = store

    def ensure_seeded(self, provider: str = PREFERRED_PROVIDER) -> None:
        row = self.store.fetchone(
            "SELECT COUNT(*) AS c FROM pcp_capabilities WHERE provider=?",
            (provider,),
        )
        if row and int(row["c"]) > 0:
            return
        now = time.time()
        for ep in ALPACA_ENDPOINTS:
            self.store.execute(
                """INSERT INTO pcp_capabilities(
                    id, provider, endpoint_family, method, auth_category, required_scope,
                    pagination, rate_limit, timestamp_behaviour, schema_notes, retention_limits,
                    error_behaviour, canary_relevance, allowed_or_forbidden, source_evidence,
                    detail_json, created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    _uid("cap"), provider, ep["endpoint_family"], ep["method"],
                    ep["auth_category"], ep["required_scope"], ep["pagination"],
                    ep["rate_limit"], ep["timestamp_behaviour"], ep["schema_notes"],
                    ep["retention_limits"], ep["error_behaviour"], ep["canary_relevance"],
                    ep["allowed_or_forbidden"], ep["source_evidence"],
                    json.dumps({"path_pattern": ep.get("path_pattern", ""), "retrieval_date": RETRIEVAL_DATE}),
                    now,
                ),
            )
        for s in PROPOSED_READ_ONLY_SCOPES + FORBIDDEN_SCOPES:
            self.store.execute(
                """INSERT INTO pcp_scopes(id, provider, scope_name, kind, rationale, source_evidence, created_at)
                   VALUES(?,?,?,?,?,?,?)""",
                (
                    _uid("scp"), provider, s["scope_name"], s["kind"],
                    s["rationale"], s["source_evidence"], now,
                ),
            )
        self.store.audit("capabilities.seeded", subject=provider, detail={"endpoints": len(ALPACA_ENDPOINTS)})

    def map(self, provider: str = PREFERRED_PROVIDER) -> dict[str, Any]:
        self.ensure_seeded(provider)
        rows = self.store.fetchall(
            "SELECT * FROM pcp_capabilities WHERE provider=? ORDER BY endpoint_family",
            (provider,),
        )
        endpoints = []
        for r in rows:
            detail = json.loads(r.pop("detail_json") or "{}")
            r["path_pattern"] = detail.get("path_pattern", "")
            endpoints.append(r)
        by_cat: dict[str, list[str]] = {}
        for e in endpoints:
            by_cat.setdefault(e["auth_category"], []).append(e["endpoint_family"])
        return {
            "provider": provider,
            "provider_adapter_implemented": PROVIDER_ADAPTER_IMPLEMENTED,
            "retrieval_date": RETRIEVAL_DATE,
            "endpoints": endpoints,
            "by_auth_category": by_cat,
            "count": len(endpoints),
            "evidence_hash": evidence_hash(endpoints),
            "REAL_CONNECTIVITY_AUTHORIZED": False,
        }

    def scopes(self, provider: str = PREFERRED_PROVIDER) -> dict[str, Any]:
        self.ensure_seeded(provider)
        rows = self.store.fetchall(
            "SELECT scope_name, kind, rationale, source_evidence FROM pcp_scopes WHERE provider=?",
            (provider,),
        )
        proposed = [r for r in rows if r["kind"] == "PROPOSED_READ_ONLY"]
        forbidden = [r for r in rows if r["kind"] == "FORBIDDEN"]
        return {
            "provider": provider,
            "proposed_read_only_scopes": proposed,
            "forbidden_scopes": forbidden,
            "mixed_scope_accepted": False,
            "provider_adapter_implemented": False,
            "REAL_CONNECTIVITY_AUTHORIZED": False,
            "evidence_hash": evidence_hash(rows),
        }

    def reject_mixed_scope(self, scopes: list[str]) -> dict[str, Any]:
        forbidden_names = {s["scope_name"] for s in FORBIDDEN_SCOPES}
        hits = [s for s in scopes if s in forbidden_names or "write" in s.lower() or "withdraw" in s.lower()]
        if hits:
            return {
                "ok": False,
                "code": "MIXED_OR_WRITE_SCOPE_REJECTED",
                "rejected_scopes": hits,
                "REAL_CONNECTIVITY_AUTHORIZED": False,
            }
        return {"ok": True, "scopes": scopes, "REAL_CONNECTIVITY_AUTHORIZED": False}
