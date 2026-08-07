"""Provider transport guard for canary planning certification.

Public documentation research is separate from runtime provider transport.
Runtime provider private/authenticated traffic is always forbidden.
"""
from __future__ import annotations

import json
import time
from typing import Any
from urllib.parse import urlparse

from saathi.platform.tg.provider_canary_planning.models import (
    FORBIDDEN_PROVIDER_DOMAINS,
    REAL_PROVIDER_TRANSPORT_FORBIDDEN,
)
from saathi.platform.tg.provider_canary_planning.store import PlanningStore, _uid

LOCALHOST_HOSTS = frozenset({
    "localhost", "127.0.0.1", "0.0.0.0", "::1", "host.docker.internal",
})

# Official documentation hosts — research only, NOT account connectivity
DOCUMENTATION_HOSTS = frozenset({
    "docs.alpaca.markets", "alpaca.markets",
    "docs.kraken.com", "support.kraken.com",
    "docs.cdp.coinbase.com", "docs.cloud.coinbase.com",
    "developers.binance.com", "binance-docs.github.io",
    "www.interactivebrokers.com", "ibkrcampus.com",
    "kite.trade", "zerodha.com",
    "bybit-exchange.github.io", "www.bybit.com",
})


class TransportGuardError(Exception):
    def __init__(self, code: str, message: str, domain: str = ""):
        self.code = code
        self.message = message
        self.domain = domain
        super().__init__(f"{code}: {message}")


class TransportGuard:
    def __init__(self, store: PlanningStore | None = None):
        self.store = store
        self.attempts: list[dict[str, Any]] = []

    def extract_domain(self, url_or_host: str) -> str:
        s = (url_or_host or "").strip().lower()
        if not s:
            return ""
        if "://" not in s:
            s = "https://" + s
        try:
            return (urlparse(s).hostname or "").lower()
        except Exception:
            return s.split("/")[0].split(":")[0]

    def classify(self, url_or_host: str) -> str:
        d = self.extract_domain(url_or_host)
        if not d or d in LOCALHOST_HOSTS or d in ("fixture", "sim", "sandbox", "planning"):
            return "local"
        # Explicit private API hosts always provider
        if d in FORBIDDEN_PROVIDER_DOMAINS or d.startswith("api.") or d.startswith("paper-api."):
            # docs subdomains of known providers may be docs
            if d in DOCUMENTATION_HOSTS or d.startswith("docs.") or "docs" in d.split("."):
                if "api." not in d and "paper-api" not in d:
                    return "documentation_research"
            return "provider_or_external"
        if d in DOCUMENTATION_HOSTS or d.startswith("docs.") or d.endswith(".github.io"):
            return "documentation_research"
        return "provider_or_external"

    def _record(self, url: str, domain: str, result: str, category: str, detail: dict | None = None) -> dict[str, Any]:
        rec = {
            "attempted_url": url,
            "domain": domain,
            "result": result,
            "category": category,
            "detail": detail or {},
            "at": time.time(),
        }
        self.attempts.append(rec)
        if self.store is not None:
            self.store.execute(
                """INSERT INTO pcp_transport_blocks(id, attempted_url, domain, result, category, detail_json, created_at)
                   VALUES(?,?,?,?,?,?,?)""",
                (
                    _uid("tb"), url, domain, result, category,
                    json.dumps(detail or {}), time.time(),
                ),
            )
            self.store.audit(
                "transport.blocked" if result == REAL_PROVIDER_TRANSPORT_FORBIDDEN else "transport.classified",
                subject=domain or url,
                detail={"url": url, "result": result, "category": category},
            )
        return rec

    def assert_allowed(self, url_or_host: str) -> dict[str, Any]:
        """Runtime transport check — private provider endpoints always blocked."""
        domain = self.extract_domain(url_or_host)
        cat = self.classify(url_or_host)
        if cat == "local":
            return {
                "ok": True,
                "domain": domain or "local-fixture",
                "result": "LOCAL_SIMULATION_ONLY",
                "category": cat,
            }
        if cat == "documentation_research":
            # Research is not runtime connectivity; still record separation.
            rec = self._record(
                url_or_host, domain, "DOCUMENTATION_RESEARCH_SEPARATE_FROM_RUNTIME",
                cat, {"note": "Not classified as broker account connectivity"},
            )
            return {
                "ok": True,
                "domain": domain,
                "result": rec["result"],
                "category": cat,
                "broker_connectivity": False,
                "runtime_transport": False,
            }
        rec = self._record(
            url_or_host, domain, REAL_PROVIDER_TRANSPORT_FORBIDDEN, "provider",
            {"forbidden": True},
        )
        raise TransportGuardError(REAL_PROVIDER_TRANSPORT_FORBIDDEN, f"Blocked: {domain}", domain)

    def probe(self, url_or_host: str) -> dict[str, Any]:
        try:
            return self.assert_allowed(url_or_host)
        except TransportGuardError as e:
            return {
                "ok": False,
                "domain": e.domain,
                "result": e.code,
                "message": e.message,
                "REAL_CONNECTIVITY_AUTHORIZED": False,
            }


_guard: TransportGuard | None = None


def reset_transport_guard(store: PlanningStore | None = None) -> TransportGuard:
    global _guard
    _guard = TransportGuard(store)
    return _guard


def get_transport_guard() -> TransportGuard:
    global _guard
    if _guard is None:
        _guard = TransportGuard()
    return _guard
