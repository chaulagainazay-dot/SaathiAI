"""M228 network isolation — transport guard.

Structurally forbids real provider transport. Returns REAL_PROVIDER_TRANSPORT_FORBIDDEN.
No sockets or HTTP to real providers. Localhost/fixtures only.
"""
from __future__ import annotations

import json
import re
import time
from typing import Any
from urllib.parse import urlparse

from saathi.platform.tg.broker_readiness.models import FORBIDDEN_PROVIDER_DOMAINS
from saathi.platform.tg.broker_readiness.store import ReadinessStore, _uid

REAL_PROVIDER_TRANSPORT_FORBIDDEN = "REAL_PROVIDER_TRANSPORT_FORBIDDEN"

LOCALHOST_HOSTS = frozenset({
    "localhost", "127.0.0.1", "0.0.0.0", "::1", "host.docker.internal",
})


class TransportGuardError(Exception):
    def __init__(self, code: str, message: str, domain: str = ""):
        self.code = code
        self.message = message
        self.domain = domain
        super().__init__(f"{code}: {message}")


class TransportGuard:
    """Dependency-injected transport boundary. Adapters cannot call external domains."""

    def __init__(self, store: ReadinessStore | None = None):
        self.store = store
        self.attempts: list[dict[str, Any]] = []

    def _record(self, url: str, domain: str, result: str, detail: dict | None = None) -> dict[str, Any]:
        rec = {
            "attempted_url": url,
            "domain": domain,
            "result": result,
            "detail": detail or {},
            "at": time.time(),
        }
        self.attempts.append(rec)
        if self.store is not None:
            self.store.execute(
                """INSERT INTO br_transport_blocks(id, attempted_url, domain, result, detail_json, created_at)
                   VALUES(?,?,?,?,?,?)""",
                (
                    _uid("tb"), url, domain, result,
                    json.dumps(detail or {}), time.time(),
                ),
            )
            self.store.audit(
                "transport.blocked",
                subject=domain or url,
                detail={"url": url, "result": result},
            )
        return rec

    def extract_domain(self, url_or_host: str) -> str:
        s = (url_or_host or "").strip().lower()
        if not s:
            return ""
        if "://" not in s:
            # bare host or host/path
            s = "https://" + s
        try:
            parsed = urlparse(s)
            host = (parsed.hostname or "").lower()
            return host
        except Exception:
            return s.split("/")[0].split(":")[0]

    def is_forbidden_domain(self, domain: str) -> bool:
        d = (domain or "").lower().strip(".")
        if not d:
            return False
        if d in LOCALHOST_HOSTS:
            return False
        for forbidden in FORBIDDEN_PROVIDER_DOMAINS:
            if d == forbidden or d.endswith("." + forbidden):
                return True
        # any non-localhost non-empty host is treated as external for this milestone
        return True

    def is_localhost(self, domain: str) -> bool:
        return (domain or "").lower() in LOCALHOST_HOSTS

    def assert_allowed(self, url_or_host: str) -> dict[str, Any]:
        """Allow only empty/local simulation targets. Everything else fails closed."""
        domain = self.extract_domain(url_or_host)
        if not domain or self.is_localhost(domain) or domain in ("fixture", "sim", "sandbox"):
            return {
                "ok": True,
                "domain": domain or "local-fixture",
                "result": "LOCAL_SIMULATION_ONLY",
            }
        rec = self._record(
            url_or_host, domain, REAL_PROVIDER_TRANSPORT_FORBIDDEN,
            {"reason": "external provider domain blocked"},
        )
        raise TransportGuardError(
            REAL_PROVIDER_TRANSPORT_FORBIDDEN,
            f"Refusing transport to '{domain}'. Real provider connectivity is forbidden.",
            domain=domain,
        )

    def attempt_request(self, url: str, *, method: str = "GET", headers: dict | None = None) -> dict[str, Any]:
        """Simulated request path — never opens a socket. Always blocks non-local."""
        # Reject Authorization-like headers for storage/replay
        if headers:
            for k, v in headers.items():
                kl = str(k).lower()
                if kl in ("authorization", "x-api-key", "api-key", "x-mbx-apikey"):
                    rec = self._record(
                        url, self.extract_domain(url), REAL_PROVIDER_TRANSPORT_FORBIDDEN,
                        {"reason": "auth_header_rejected", "header": k},
                    )
                    raise TransportGuardError(
                        "AUTH_HEADER_TRANSPORT_FORBIDDEN",
                        "Authorization headers cannot be used for real transport.",
                        domain=self.extract_domain(url),
                    )
        try:
            self.assert_allowed(url)
        except TransportGuardError:
            raise
        # Even localhost is simulation-only — no real HTTP client.
        return {
            "ok": True,
            "simulated": True,
            "method": method,
            "url": url,
            "body": {"status": "SIMULATED_LOCAL_FIXTURE"},
            "note": "No network I/O performed. Fixture response only.",
        }

    def scan_for_external_attempts(self) -> dict[str, Any]:
        blocked = [a for a in self.attempts if a["result"] == REAL_PROVIDER_TRANSPORT_FORBIDDEN]
        db_rows = []
        if self.store is not None:
            db_rows = self.store.fetchall(
                "SELECT * FROM br_transport_blocks ORDER BY created_at DESC LIMIT 100"
            )
        return {
            "in_memory_attempts": len(self.attempts),
            "blocked_count": len(blocked),
            "blocked": blocked[-20:],
            "persisted_blocks": len(db_rows),
            "result": REAL_PROVIDER_TRANSPORT_FORBIDDEN if blocked or db_rows else "NO_EXTERNAL_ATTEMPTS",
            "network_isolation": True,
            "real_transport_possible": False,
        }


# Module-level guard for structural enforcement
_default_guard: TransportGuard | None = None


def default_transport_guard(store: ReadinessStore | None = None) -> TransportGuard:
    global _default_guard
    if _default_guard is None:
        _default_guard = TransportGuard(store=store)
    elif store is not None and _default_guard.store is None:
        _default_guard.store = store
    return _default_guard


def reset_transport_guard(store: ReadinessStore | None = None) -> TransportGuard:
    global _default_guard
    _default_guard = TransportGuard(store=store)
    return _default_guard


__all__ = [
    "TransportGuard",
    "TransportGuardError",
    "REAL_PROVIDER_TRANSPORT_FORBIDDEN",
    "default_transport_guard",
    "reset_transport_guard",
]
