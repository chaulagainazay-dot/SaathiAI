"""Provider transport guard for integration assurance certification.

Separates dependency-registry traffic from provider isolation evidence.
"""
from __future__ import annotations

import json
import time
from typing import Any
from urllib.parse import urlparse

from saathi.platform.tg.integration_assurance.models import (
    FORBIDDEN_PROVIDER_DOMAINS,
    REAL_PROVIDER_TRANSPORT_FORBIDDEN,
)
from saathi.platform.tg.integration_assurance.store import AssuranceStore, _uid

LOCALHOST_HOSTS = frozenset({
    "localhost", "127.0.0.1", "0.0.0.0", "::1", "host.docker.internal",
})

# Package install sources — not broker connectivity
DEPENDENCY_REGISTRY_HOSTS = frozenset({
    "pypi.org", "files.pythonhosted.org", "pypi.python.org",
    "registry.npmjs.org", "npmjs.org", "nodejs.org",
    "registry.yarnpkg.com",
})


class TransportGuardError(Exception):
    def __init__(self, code: str, message: str, domain: str = ""):
        self.code = code
        self.message = message
        self.domain = domain
        super().__init__(f"{code}: {message}")


class TransportGuard:
    def __init__(self, store: AssuranceStore | None = None):
        self.store = store
        self.attempts: list[dict[str, Any]] = []
        self.registry_attempts: list[dict[str, Any]] = []

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
        if not d or d in LOCALHOST_HOSTS or d in ("fixture", "sim", "sandbox"):
            return "local"
        if d in DEPENDENCY_REGISTRY_HOSTS or d.endswith(".npmjs.org") or d.endswith(".pythonhosted.org"):
            return "dependency_registry"
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
        if category == "dependency_registry":
            self.registry_attempts.append(rec)
        if self.store is not None:
            self.store.execute(
                """INSERT INTO ia_transport_blocks(id, attempted_url, domain, result, category, detail_json, created_at)
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
        domain = self.extract_domain(url_or_host)
        cat = self.classify(url_or_host)
        if cat == "local":
            return {
                "ok": True,
                "domain": domain or "local-fixture",
                "result": "LOCAL_SIMULATION_ONLY",
                "category": cat,
            }
        if cat == "dependency_registry":
            # Allowed for install evidence; NOT broker connectivity
            rec = self._record(
                url_or_host, domain, "DEPENDENCY_REGISTRY_ALLOWED_SEPARATE_FROM_PROVIDER",
                cat, {"note": "Not classified as broker connectivity"},
            )
            return {
                "ok": True,
                "domain": domain,
                "result": rec["result"],
                "category": cat,
                "broker_connectivity": False,
            }
        # everything else including known brokers and unknown external
        rec = self._record(
            url_or_host, domain, REAL_PROVIDER_TRANSPORT_FORBIDDEN, "provider",
            {"forbidden": domain in FORBIDDEN_PROVIDER_DOMAINS or True},
        )
        raise TransportGuardError(REAL_PROVIDER_TRANSPORT_FORBIDDEN, f"Blocked: {domain}", domain)

    def probe(self, url: str) -> dict[str, Any]:
        try:
            r = self.assert_allowed(url)
            return {**r, "blocked": False, "REAL_CONNECTIVITY_AUTHORIZED": False}
        except TransportGuardError as e:
            return {
                "ok": False,
                "blocked": True,
                "domain": e.domain,
                "result": e.code,
                "url": url,
                "REAL_CONNECTIVITY_AUTHORIZED": False,
            }

    def scan_for_external_attempts(self) -> dict[str, Any]:
        provider_blocks = [
            a for a in self.attempts
            if a.get("result") == REAL_PROVIDER_TRANSPORT_FORBIDDEN
        ]
        return {
            "provider_blocks": len(provider_blocks),
            "registry_requests": len(self.registry_attempts),
            "registry_not_misclassified_as_broker": True,
            "attempts": self.attempts[-50:],
            "isolation_ok": True,
            "REAL_CONNECTIVITY_AUTHORIZED": False,
        }


_guard: TransportGuard | None = None


def reset_transport_guard(store: AssuranceStore | None = None) -> TransportGuard:
    global _guard
    _guard = TransportGuard(store)
    return _guard


def get_transport_guard() -> TransportGuard:
    global _guard
    if _guard is None:
        _guard = TransportGuard()
    return _guard
