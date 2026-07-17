"""M27 — Governed HTTP adapter (injectable transport; no secrets in evidence)."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional
from urllib.parse import urlparse

from saathi.connectors.gov.models import ConnectorRequest, ConnectorResult
from saathi.connectors.gov.redaction import redact_payload

ALLOWED_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"})


TransportFn = Callable[[str, str, dict[str, str], Optional[bytes], float], dict[str, Any]]


def default_transport(
    method: str,
    url: str,
    headers: dict[str, str],
    body: Optional[bytes],
    timeout: float,
) -> dict[str, Any]:
    """Real transport using httpx — only used when explicitly enabled in production wiring.

    M27 tests inject stubs. This path still strips auth headers from returned evidence.
    """
    import httpx

    with httpx.Client(timeout=timeout, follow_redirects=False) as client:
        r = client.request(method, url, headers=headers, content=body)
        return {
            "status_code": r.status_code,
            "headers": {k: v for k, v in r.headers.items() if k.lower() not in {
                "set-cookie", "authorization", "cookie", "www-authenticate",
            }},
            "body_preview": (r.text or "")[:500],
            "ok": 200 <= r.status_code < 300,
        }


@dataclass
class HttpAdapter:
    """Governed HTTP execution with timeout/retry bounds."""

    transport: TransportFn = default_transport
    name: str = "http"

    def execute(
        self,
        request: ConnectorRequest,
        *,
        timeout_seconds: float = 30.0,
        max_retries: int = 1,
    ) -> ConnectorResult:
        method = (request.method or "GET").upper()
        if method not in ALLOWED_METHODS:
            return ConnectorResult(
                ok=False,
                connector_id=request.connector_id,
                operation=request.operation,
                status="error",
                detail=f"method_not_allowed:{method}",
            )
        url = (request.url or request.payload.get("url") or "").strip()
        if not url:
            return ConnectorResult(
                ok=False,
                connector_id=request.connector_id,
                operation=request.operation,
                status="error",
                detail="url_required",
            )
        host = (urlparse(url).hostname or "").lower()
        # Never send Authorization headers through this adapter in M27 framework path
        headers = {
            k: v
            for k, v in (request.headers or {}).items()
            if k.lower() not in ("authorization", "cookie", "x-api-key", "proxy-authorization")
        }
        body = None
        if method in ("POST", "PUT", "PATCH"):
            payload = {k: v for k, v in (request.payload or {}).items() if k != "url"}
            body = json.dumps(payload).encode("utf-8")
            headers.setdefault("content-type", "application/json")

        attempts = 0
        last_err = ""
        t0 = time.perf_counter()
        max_attempts = max(1, int(max_retries) + 1)
        while attempts < max_attempts:
            attempts += 1
            try:
                raw = self.transport(method, url, headers, body, float(timeout_seconds))
                ok = bool(raw.get("ok"))
                data = redact_payload({
                    "status_code": raw.get("status_code"),
                    "host": host,
                    "method": method,
                    "body_preview": raw.get("body_preview"),
                    "headers": raw.get("headers") or {},
                })
                return ConnectorResult(
                    ok=ok,
                    connector_id=request.connector_id,
                    operation=request.operation,
                    status="success" if ok else "error",
                    detail="http_ok" if ok else f"http_status:{raw.get('status_code')}",
                    data=data if isinstance(data, dict) else {"raw": str(data)},
                    attempts=attempts,
                    latency_ms=round((time.perf_counter() - t0) * 1000, 2),
                    privacy_safe=True,
                    bypass=False,
                )
            except TimeoutError as e:
                last_err = "timeout"
                if attempts >= max_attempts:
                    return ConnectorResult(
                        ok=False,
                        connector_id=request.connector_id,
                        operation=request.operation,
                        status="timeout",
                        detail="timeout",
                        attempts=attempts,
                        latency_ms=round((time.perf_counter() - t0) * 1000, 2),
                    )
            except Exception as e:
                last_err = type(e).__name__
                if attempts >= max_attempts:
                    return ConnectorResult(
                        ok=False,
                        connector_id=request.connector_id,
                        operation=request.operation,
                        status="error",
                        detail=last_err,
                        attempts=attempts,
                        latency_ms=round((time.perf_counter() - t0) * 1000, 2),
                    )
        return ConnectorResult(
            ok=False,
            connector_id=request.connector_id,
            operation=request.operation,
            status="error",
            detail=last_err or "http_failed",
            attempts=attempts,
            latency_ms=round((time.perf_counter() - t0) * 1000, 2),
        )
