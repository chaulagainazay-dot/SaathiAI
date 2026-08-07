"""M314 Provider Governance Registry — governance only, no connections."""
from __future__ import annotations

import re
import time
from typing import Any

from saathi.platform.tg.connectivity_governance.errors import ProviderGovernanceError
from saathi.platform.tg.connectivity_governance.models import (
    AUTHORITY_VALUES,
    MAX_PROVIDER_STATE,
    PROHIBITED_OPERATIONS,
    ProviderGovernanceState,
)

# Capability / domain allowlists (governance names only)
APPROVED_CAPABILITY_NAMES = frozenset({
    "offline_fixture_access",
    "public_unauthenticated_data",
    "authenticated_market_data",
    "historical_refresh",
    "real_time_quote_stream",
    "account_metadata",
    "balances",
    "positions",
    "orders",
    "fills",
    "activity",
    "margin_state",
    "submit_order",
    "modify_order",
    "cancel_order",
    "transfer",
    "withdraw",
    "change_settings",
    "internal_simulation",
    "external_paper",
    "live_execution",
    "credential_reference_creation",
    "credential_validation",
    "credential_use",
    "credential_rotation",
    "credential_revocation",
})

APPROVED_AUTH_METHODS = frozenset({
    "none",
    "api_key_header",  # documented method only — not usable this milestone
    "oauth2_authorization_code",  # documented — not authorized
    "hmac_signature",
    "mtls",
})

PROHIBITED_ENDPOINT_CLASSES = frozenset({
    "withdrawal",
    "transfer",
    "live_order",
    "account_settings_change",
    "credential_export",
    "unrestricted_oauth",
    "wildcard_domain",
    "unverified_sdk",
    "unofficial_proxy",
})

PROHIBITED_CAPABILITIES_BLOCKLIST = frozenset({
    "withdrawal",
    "transfer",
    "live_order",
    "account_settings_changes",
    "credential_export",
    "unrestricted_oauth",
    "wildcard_domains",
    "unverified_sdks",
    "unofficial_proxy_endpoints",
    "live_execution",
    "withdraw",
})

# Seeded research-only / documentation-reviewed providers (no connection)
SEED_PROVIDERS = [
    {
        "provider_id": "prov_alpaca_paper_docs",
        "provider_name": "Alpaca Markets (documentation review)",
        "provider_type": "broker_api",
        "jurisdiction": "US",
        "legal_entity": "Alpaca Securities LLC (documented)",
        "official_domains": ["alpaca.markets", "docs.alpaca.markets"],
        "api_host_patterns": ["api.alpaca.markets", "paper-api.alpaca.markets", "data.alpaca.markets"],
        "documented_api_families": ["trading", "market_data", "broker"],
        "authentication_methods": ["api_key_header", "oauth2_authorization_code"],
        "market_data_capabilities": ["historical_refresh", "real_time_quote_stream"],
        "account_read_capabilities": ["account_metadata", "balances", "positions", "orders", "fills"],
        "paper_execution_capabilities": ["external_paper"],
        "live_execution_capabilities": ["live_execution"],
        "transfer_capabilities": ["transfer"],
        "withdrawal_capabilities": ["withdraw"],
        "credential_types": ["api_key_secret_pair"],
        "rate_limit_posture": "documented_per_endpoint",
        "sandbox_availability": True,
        "paper_environment_availability": True,
        "geographic_restrictions": ["US-centric documentation review only"],
        "account_restrictions": ["no account access this milestone"],
        "data_licensing_considerations": ["review required before any canary"],
        "operational_risks": ["credential leakage", "paper/live confusion", "rate limits"],
        "approval_status": "documentation_reviewed",
        "governance_status": ProviderGovernanceState.DOCUMENTATION_REVIEWED.value,
        "evidence_references": ["m240_m247_provider_canary_planning", "public_docs_only"],
        "limitations": [
            "Governance record only — no connection",
            "No credentials",
            "No canary activation",
            "Live execution remains prohibited",
        ],
        "active": False,
        "connected": False,
    },
    {
        "provider_id": "prov_ibkr_docs",
        "provider_name": "Interactive Brokers (documentation review)",
        "provider_type": "broker_api",
        "jurisdiction": "MULTI",
        "legal_entity": "Interactive Brokers LLC (documented)",
        "official_domains": ["interactivebrokers.com", "www.interactivebrokers.com"],
        "api_host_patterns": ["api.ibkr.com", "localhost:5000"],  # Client Portal documented local
        "documented_api_families": ["client_portal", "tws"],
        "authentication_methods": ["oauth2_authorization_code", "session_cookie"],
        "market_data_capabilities": ["authenticated_market_data", "historical_refresh"],
        "account_read_capabilities": ["account_metadata", "balances", "positions", "orders"],
        "paper_execution_capabilities": ["external_paper"],
        "live_execution_capabilities": ["live_execution"],
        "transfer_capabilities": ["transfer"],
        "withdrawal_capabilities": ["withdraw"],
        "credential_types": ["username_password", "oauth"],
        "rate_limit_posture": "session_based",
        "sandbox_availability": True,
        "paper_environment_availability": True,
        "geographic_restrictions": ["jurisdiction review required"],
        "account_restrictions": ["no account access this milestone"],
        "data_licensing_considerations": ["market data subscriptions"],
        "operational_risks": ["session cookies", "gateway complexity", "live/paper confusion"],
        "approval_status": "documentation_reviewed",
        "governance_status": ProviderGovernanceState.DOCUMENTATION_REVIEWED.value,
        "evidence_references": ["public_docs_only"],
        "limitations": ["Governance only — no connection", "OAuth not authorized"],
        "active": False,
        "connected": False,
    },
    {
        "provider_id": "prov_binance_docs",
        "provider_name": "Binance (documentation review)",
        "provider_type": "exchange_api",
        "jurisdiction": "VARIES",
        "legal_entity": "jurisdiction-dependent (documented)",
        "official_domains": ["binance.com", "www.binance.com", "binance.us"],
        "api_host_patterns": ["api.binance.com", "api.binance.us"],
        "documented_api_families": ["spot", "futures", "wallet"],
        "authentication_methods": ["hmac_signature", "api_key_header"],
        "market_data_capabilities": ["public_unauthenticated_data", "authenticated_market_data"],
        "account_read_capabilities": ["balances", "positions", "orders", "fills"],
        "paper_execution_capabilities": [],
        "live_execution_capabilities": ["live_execution"],
        "transfer_capabilities": ["transfer"],
        "withdrawal_capabilities": ["withdraw"],
        "credential_types": ["api_key_secret_pair"],
        "rate_limit_posture": "weight_based",
        "sandbox_availability": True,
        "paper_environment_availability": False,
        "geographic_restrictions": ["severe geo restrictions; jurisdiction unresolved for many regions"],
        "account_restrictions": ["no account access this milestone"],
        "data_licensing_considerations": ["exchange terms apply"],
        "operational_risks": ["withdrawal paths", "geo blocks", "API key privilege levels"],
        "approval_status": "research_only",
        "governance_status": ProviderGovernanceState.RESEARCH_ONLY.value,
        "evidence_references": ["public_docs_only"],
        "limitations": [
            "Jurisdiction often unresolved",
            "Withdrawal capabilities present in API surface — blocked",
            "No connection",
        ],
        "active": False,
        "connected": False,
    },
    {
        "provider_id": "prov_mock_contract",
        "provider_name": "Synthetic Mock Provider (governance)",
        "provider_type": "mock",
        "jurisdiction": "N/A",
        "legal_entity": "internal_synthetic",
        "official_domains": ["localhost"],
        "api_host_patterns": ["127.0.0.1", "localhost"],
        "documented_api_families": ["mock_contract"],
        "authentication_methods": ["none"],
        "market_data_capabilities": ["offline_fixture_access"],
        "account_read_capabilities": [],
        "paper_execution_capabilities": ["internal_simulation"],
        "live_execution_capabilities": [],
        "transfer_capabilities": [],
        "withdrawal_capabilities": [],
        "credential_types": [],
        "rate_limit_posture": "none",
        "sandbox_availability": True,
        "paper_environment_availability": True,
        "geographic_restrictions": [],
        "account_restrictions": ["no real accounts"],
        "data_licensing_considerations": ["synthetic fixtures only"],
        "operational_risks": ["none material for mock"],
        "approval_status": "mock_eligible",
        "governance_status": ProviderGovernanceState.MOCK_ELIGIBLE.value,
        "evidence_references": ["m304_m311_offline_fixtures"],
        "limitations": ["Mock/synthetic only — no external network"],
        "active": False,
        "connected": False,
    },
]


def _validate_domains(domains: list[str]) -> None:
    for d in domains:
        if "*" in d or d.startswith("."):
            raise ProviderGovernanceError("WILDCARD_DOMAIN_REJECTED", f"Wildcard domain forbidden: {d}")
        if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9.-]+[a-zA-Z0-9]$|^localhost$|^127\.0\.0\.1$", d):
            # allow simple hostnames
            if d not in ("localhost", "127.0.0.1"):
                if "://" in d:
                    raise ProviderGovernanceError("INVALID_DOMAIN", f"Domain must not include scheme: {d}")


def _validate_capabilities(caps: list[str]) -> None:
    for c in caps:
        if c not in APPROVED_CAPABILITY_NAMES and c not in PROHIBITED_CAPABILITIES_BLOCKLIST:
            raise ProviderGovernanceError("UNSUPPORTED_CAPABILITY", f"Unknown capability: {c}")
        if c in ("live_execution", "withdraw", "transfer") and False:
            pass  # may be listed as documented capability but not activated


class ProviderRegistry:
    def __init__(self):
        self._providers: dict[str, dict[str, Any]] = {}
        for p in SEED_PROVIDERS:
            rec = dict(p)
            rec["registered_at"] = time.time()
            rec["connection_established"] = False
            self._providers[rec["provider_id"]] = rec

    def list_providers(self) -> dict[str, Any]:
        items = list(self._providers.values())
        return {
            "ok": True,
            "count": len(items),
            "providers": items,
            "any_active": False,
            "any_connected": False,
            "max_provider_state": MAX_PROVIDER_STATE,
            **AUTHORITY_VALUES,
        }

    def get_provider(self, provider_id: str) -> dict[str, Any]:
        p = self._providers.get(provider_id)
        if not p:
            return {"ok": False, "error": "PROVIDER_NOT_FOUND", "provider_id": provider_id}
        return {"ok": True, "provider": p, "connected": False, **AUTHORITY_VALUES}

    def register_provider(self, record: dict[str, Any], *, actor: str) -> dict[str, Any]:
        if not actor or actor.lower() in ("llm", "ai", "agent", "model"):
            raise ProviderGovernanceError("HUMAN_ACTOR_REQUIRED", "Human actor required for provider registration")
        pid = record.get("provider_id") or f"prov_{int(time.time())}"
        domains = list(record.get("official_domains") or [])
        _validate_domains(domains)
        hosts = list(record.get("api_host_patterns") or [])
        _validate_domains(hosts)
        status = record.get("governance_status", ProviderGovernanceState.UNREVIEWED.value)
        allowed = {
            ProviderGovernanceState.UNREVIEWED.value,
            ProviderGovernanceState.RESEARCH_ONLY.value,
            ProviderGovernanceState.DOCUMENTATION_REVIEWED.value,
            ProviderGovernanceState.MOCK_ELIGIBLE.value,
            ProviderGovernanceState.PROHIBITED.value,
        }
        if status not in allowed:
            raise ProviderGovernanceError(
                "PROVIDER_STATE_TOO_HIGH",
                f"Max provider state this milestone is {MAX_PROVIDER_STATE}; got {status}",
            )
        if status in (
            ProviderGovernanceState.READ_ONLY_CANARY_ELIGIBLE.value,
            ProviderGovernanceState.EXTERNAL_PAPER_CANARY_ELIGIBLE.value,
        ):
            raise ProviderGovernanceError("CANARY_STATE_FORBIDDEN", "Canary-eligible states not allowed in M312-M319")
        rec = {
            "provider_id": pid,
            "provider_name": record.get("provider_name", pid),
            "provider_type": record.get("provider_type", "unknown"),
            "jurisdiction": record.get("jurisdiction", "UNRESOLVED"),
            "legal_entity": record.get("legal_entity", "unknown"),
            "official_domains": domains,
            "api_host_patterns": hosts,
            "documented_api_families": list(record.get("documented_api_families") or []),
            "authentication_methods": list(record.get("authentication_methods") or ["none"]),
            "market_data_capabilities": list(record.get("market_data_capabilities") or []),
            "account_read_capabilities": list(record.get("account_read_capabilities") or []),
            "paper_execution_capabilities": list(record.get("paper_execution_capabilities") or []),
            "live_execution_capabilities": list(record.get("live_execution_capabilities") or []),
            "transfer_capabilities": list(record.get("transfer_capabilities") or []),
            "withdrawal_capabilities": list(record.get("withdrawal_capabilities") or []),
            "credential_types": list(record.get("credential_types") or []),
            "rate_limit_posture": record.get("rate_limit_posture", "unknown"),
            "sandbox_availability": bool(record.get("sandbox_availability", False)),
            "paper_environment_availability": bool(record.get("paper_environment_availability", False)),
            "geographic_restrictions": list(record.get("geographic_restrictions") or []),
            "account_restrictions": list(record.get("account_restrictions") or ["no account access"]),
            "data_licensing_considerations": list(record.get("data_licensing_considerations") or []),
            "operational_risks": list(record.get("operational_risks") or []),
            "approval_status": record.get("approval_status", "unreviewed"),
            "governance_status": status,
            "evidence_references": list(record.get("evidence_references") or []),
            "limitations": list(record.get("limitations") or ["governance only"]),
            "active": False,
            "connected": False,
            "connection_established": False,
            "registered_by": actor,
            "registered_at": time.time(),
        }
        self._providers[pid] = rec
        return {"ok": True, "provider": rec, "connected": False, **AUTHORITY_VALUES}

    def prohibit_provider(self, provider_id: str, *, actor: str, reason: str) -> dict[str, Any]:
        p = self._providers.get(provider_id)
        if not p:
            return {"ok": False, "error": "PROVIDER_NOT_FOUND"}
        p["governance_status"] = ProviderGovernanceState.PROHIBITED.value
        p["approval_status"] = "prohibited"
        p["prohibited_by"] = actor
        p["prohibited_reason"] = reason
        p["active"] = False
        p["connected"] = False
        return {"ok": True, "provider": p, **AUTHORITY_VALUES}

    def capability_policy(self) -> dict[str, Any]:
        return {
            "ok": True,
            "approved_capability_names": sorted(APPROVED_CAPABILITY_NAMES),
            "approved_authentication_methods": sorted(APPROVED_AUTH_METHODS),
            "prohibited_endpoint_classes": sorted(PROHIBITED_ENDPOINT_CLASSES),
            "prohibited_capabilities_blocklist": sorted(PROHIBITED_CAPABILITIES_BLOCKLIST),
            "prohibited_operations": sorted(PROHIBITED_OPERATIONS),
            "wildcard_domains_allowed": False,
            "unverified_sdks_allowed": False,
            "max_provider_state": MAX_PROVIDER_STATE,
            "any_provider_active": False,
            **AUTHORITY_VALUES,
        }

    def domain_allowlists(self) -> dict[str, Any]:
        domains = set()
        hosts = set()
        docs = set()
        for p in self._providers.values():
            domains.update(p.get("official_domains") or [])
            hosts.update(p.get("api_host_patterns") or [])
            for d in p.get("official_domains") or []:
                if "docs" in d or d.startswith("docs."):
                    docs.add(d)
        return {
            "ok": True,
            "approved_official_domains": sorted(domains),
            "approved_api_host_patterns": sorted(hosts),
            "approved_documentation_sources": sorted(docs) or ["docs.alpaca.markets"],
            "wildcard_domains": [],
            **AUTHORITY_VALUES,
        }

    def export_registry(self) -> dict[str, Any]:
        return {
            "schema": "M314_PROVIDER_GOVERNANCE_REGISTRY",
            "providers": self.list_providers(),
            "capability_policy": self.capability_policy(),
            "domain_allowlists": self.domain_allowlists(),
            "governance_only": True,
            "connection_established": False,
            **AUTHORITY_VALUES,
        }
