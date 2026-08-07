"""Official source inventory for M240 provider research.

Research uses official documentation URLs. Retrieval date is recorded.
Documentation research is NOT provider account connectivity.
"""
from __future__ import annotations

import json
import time
from typing import Any

from saathi.platform.tg.provider_canary_planning.models import RETRIEVAL_DATE
from saathi.platform.tg.provider_canary_planning.store import PlanningStore, _uid, evidence_hash

# Seeded official-primary sources with retrieval metadata (2026-07-30).
OFFICIAL_SOURCES: list[dict[str, Any]] = [
    {
        "provider": "alpaca",
        "title": "Alpaca Docs — Getting Started",
        "url": "https://docs.alpaca.markets/docs/getting-started",
        "category": "official_api_docs",
        "relevant_claim": "Alpaca offers Trading API, Market Data API, Broker API, paper trading and OAuth Connect.",
        "confidence": "high",
        "unresolved_ambiguity": "Owner geographic eligibility and product entitlements require owner confirmation.",
    },
    {
        "provider": "alpaca",
        "title": "Alpaca Trading API Getting Started",
        "url": "https://docs.alpaca.markets/docs/getting-started-with-trading-api",
        "category": "official_api_docs",
        "relevant_claim": "Trading API supports account, positions, orders, portfolio history for individuals/business accounts.",
        "confidence": "high",
        "unresolved_ambiguity": "Exact paper vs live key separation and IP allow-list UI path needs owner console verification.",
    },
    {
        "provider": "alpaca",
        "title": "Alpaca Paper Trading environment (paper-api.alpaca.markets)",
        "url": "https://docs.alpaca.markets/docs/paper-trading",
        "category": "official_sandbox_testnet",
        "relevant_claim": "Paper trading environment available separate from live; keys target paper-api host.",
        "confidence": "medium",
        "unresolved_ambiguity": "Current paper host and key isolation documented in dashboard; verify at canary time.",
    },
    {
        "provider": "kraken",
        "title": "Kraken API key permissions guide",
        "url": "https://docs.kraken.com/exchange/guides/rest/api-keys",
        "category": "official_permission_scopes",
        "relevant_claim": "Granular permissions: Query Funds; Query Open/Closed Orders & Trades; separate withdraw and trade permissions.",
        "confidence": "high",
        "unresolved_ambiguity": "IP allow-list and key expiry options need console verification by owner.",
    },
    {
        "provider": "kraken",
        "title": "Kraken Get API Key Info",
        "url": "https://docs.kraken.com/api-reference/account-data/get-api-key-info",
        "category": "official_security_docs",
        "relevant_claim": "GetApiKeyInfo returns key permissions including query-funds and withdraw-funds for introspection.",
        "confidence": "high",
        "unresolved_ambiguity": "Whether all future permission strings are stable across API versions.",
    },
    {
        "provider": "coinbase",
        "title": "Coinbase Advanced Trade API product page",
        "url": "https://www.coinbase.com/developer-platform/products/advanced-trade-api",
        "category": "official_api_docs",
        "relevant_claim": "CDP API keys support permission configuration; IP whitelist encouraged; keys may not expire by default.",
        "confidence": "medium",
        "unresolved_ambiguity": "Default non-expiring keys increase residual risk; owner must force rotation policy.",
    },
    {
        "provider": "coinbase",
        "title": "Get API Key Permissions (Advanced Trade)",
        "url": "https://docs.cdp.coinbase.com/api-reference/advanced-trade-api/rest-api/data-api/get-api-key-permissions",
        "category": "official_permission_scopes",
        "relevant_claim": "can_view / can_trade / can_transfer permission flags enable read/write/transfer separation.",
        "confidence": "high",
        "unresolved_ambiguity": "Portfolio UUID binding and multi-portfolio isolation require owner confirmation.",
    },
    {
        "provider": "coinbase",
        "title": "Coinbase Business OAuth2 Scopes",
        "url": "https://docs.cdp.coinbase.com/coinbase-business/authentication-authorization/oauth2/scopes",
        "category": "official_permission_scopes",
        "relevant_claim": "Fine-grained OAuth scopes exist; canary planning prefers non-OAuth API key path if available.",
        "confidence": "medium",
        "unresolved_ambiguity": "OAuth is forbidden for M240-M247 runtime; future use needs separate security review.",
    },
    {
        "provider": "binance",
        "title": "Binance API Terms / product page",
        "url": "https://www.binance.com/en/binance-api",
        "category": "official_api_terms",
        "relevant_claim": "Official API product exists with documentation and sample code; API keys created via account.",
        "confidence": "medium",
        "unresolved_ambiguity": "Entity (global vs regional) and residency restrictions are jurisdiction-specific and unresolved for owner.",
    },
    {
        "provider": "binance",
        "title": "Binance Developer Docs — Account/Wallet REST",
        "url": "https://developers.binance.com/en/docs/catalog/core-trading-wallet/api/rest-api/account",
        "category": "official_api_docs",
        "relevant_claim": "Authenticated account endpoints require API key; restriction model includes trading/withdrawal separation.",
        "confidence": "medium",
        "unresolved_ambiguity": "Geographic product availability and KYC requirements owner-specific.",
    },
    {
        "provider": "interactive_brokers",
        "title": "Interactive Brokers Client Portal / Web API documentation hub",
        "url": "https://www.interactivebrokers.com/campus/ibkr-api-page/cpapi-v1/",
        "category": "official_api_docs",
        "relevant_claim": "IBKR provides Client Portal Web API and TWS/Gateway APIs; authentication model is session/OAuth oriented.",
        "confidence": "medium",
        "unresolved_ambiguity": "Complexity of gateway/session model elevates operational risk for a first canary.",
    },
    {
        "provider": "zerodha",
        "title": "Kite Connect API documentation",
        "url": "https://kite.trade/docs/connect/v3/",
        "category": "official_api_docs",
        "relevant_claim": "Kite Connect supports account, holdings, positions, orders for Indian markets; login token model.",
        "confidence": "medium",
        "unresolved_ambiguity": "Primarily India-resident product; owner residency eligibility unconfirmed.",
    },
    {
        "provider": "bybit",
        "title": "Bybit API documentation",
        "url": "https://bybit-exchange.github.io/docs/v5/intro",
        "category": "official_api_docs",
        "relevant_claim": "Bybit V5 API covers account, positions, order history with API key permissions.",
        "confidence": "medium",
        "unresolved_ambiguity": "Regional restrictions and derivatives focus may misalign with initial equity-first roadmap.",
    },
]


class SourceInventory:
    def __init__(self, store: PlanningStore):
        self.store = store

    def seed_if_empty(self) -> dict[str, Any]:
        existing = self.store.fetchone("SELECT COUNT(*) AS c FROM pcp_sources")
        if existing and int(existing["c"]) > 0:
            return self.list_sources()
        now = time.time()
        for s in OFFICIAL_SOURCES:
            self.store.execute(
                """INSERT INTO pcp_sources(
                    id, provider, title, url, retrieval_date, category,
                    relevant_claim, confidence, unresolved_ambiguity, detail_json, created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    _uid("src"), s["provider"], s["title"], s["url"], RETRIEVAL_DATE,
                    s["category"], s["relevant_claim"], s["confidence"],
                    s.get("unresolved_ambiguity", ""), json.dumps({}), now,
                ),
            )
        self.store.audit("sources.seeded", detail={"count": len(OFFICIAL_SOURCES), "retrieval_date": RETRIEVAL_DATE})
        return self.list_sources()

    def list_sources(self, provider: str | None = None) -> dict[str, Any]:
        if provider:
            rows = self.store.fetchall(
                "SELECT * FROM pcp_sources WHERE provider=? ORDER BY created_at",
                (provider,),
            )
        else:
            rows = self.store.fetchall("SELECT * FROM pcp_sources ORDER BY provider, created_at")
        for r in rows:
            r.pop("detail_json", None)
        return {
            "retrieval_date": RETRIEVAL_DATE,
            "count": len(rows),
            "sources": rows,
            "note": "Documentation research is separate from runtime provider transport.",
            "REAL_CONNECTIVITY_AUTHORIZED": False,
            "evidence_hash": evidence_hash(rows),
        }
