"""Bounded HTTP client for allowlisted InsForge GET endpoints only."""
from __future__ import annotations

import json
from typing import Any, Callable
from urllib.parse import urljoin, urlparse

from saathi.providers.insforge.config import (
    ALLOWED_PATHS,
    InsForgeConfig,
    is_path_allowed,
    is_path_blocked,
    validate_base_url,
)
from saathi.providers.insforge.errors import InsForgeError, InsForgeErrorCategory

# Injectable for tests
TransportFactory = Callable[..., Any]


# POST allowlist for M18.4 migration pilot only (never open)
WRITE_ALLOWED_PATHS: frozenset[str] = frozenset({
    "/api/database/migrations",
})


class InsForgeClient:
    """HTTP client: GET allowlist + single POST migration path when writes enabled."""

    def __init__(self, config: InsForgeConfig, *, transport: Any = None):
        self.config = config
        self._transport = transport

    def get_json(self, path: str, *, params: dict | None = None) -> dict | list:
        return self._request("GET", path, params=params)

    def post_json(self, path: str, *, json_body: dict | None = None) -> dict | list:
        """Migration-only POST. Requires writes_enabled + path allowlist."""
        if not getattr(self.config, "writes_enabled", False):
            raise InsForgeError(
                InsForgeErrorCategory.WRITE_FORBIDDEN, "writes_disabled",
            )
        path = (path or "").strip()
        if not path.startswith("/"):
            path = "/" + path
        clean = path.split("?", 1)[0].rstrip("/") or path
        if clean not in WRITE_ALLOWED_PATHS:
            raise InsForgeError(
                InsForgeErrorCategory.SECURITY_POLICY_DENIED,
                f"write_path_not_allowlisted:{clean[:80]}",
            )
        return self._request("POST", path, json_body=json_body)

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        json_body: dict | None = None,
    ) -> dict | list:
        cfg = self.config
        if not cfg.enabled:
            raise InsForgeError(InsForgeErrorCategory.PROVIDER_DISABLED, "insforge disabled")

        ok, reason = validate_base_url(cfg.base_url, allow_loopback=cfg.allow_loopback)
        if not ok:
            raise InsForgeError(InsForgeErrorCategory.CONFIGURATION_INVALID, reason)

        path = (path or "").strip()
        if not path.startswith("/"):
            path = "/" + path
        method_u = method.upper()
        if method_u == "GET":
            if is_path_blocked(path):
                raise InsForgeError(
                    InsForgeErrorCategory.SECURITY_POLICY_DENIED,
                    f"path_blocked:{path.split('?',1)[0][:80]}",
                )
            if not is_path_allowed(path):
                raise InsForgeError(
                    InsForgeErrorCategory.SECURITY_POLICY_DENIED,
                    f"path_not_allowlisted:{path.split('?',1)[0][:80]}",
                )
        elif method_u == "POST":
            clean = path.split("?", 1)[0].rstrip("/")
            if clean not in WRITE_ALLOWED_PATHS:
                raise InsForgeError(
                    InsForgeErrorCategory.WRITE_FORBIDDEN,
                    f"post_not_allowlisted:{clean[:80]}",
                )
        else:
            raise InsForgeError(
                InsForgeErrorCategory.WRITE_FORBIDDEN,
                f"method_denied:{method_u}",
            )

        url = urljoin(cfg.base_url.rstrip("/") + "/", path.lstrip("/"))
        base_host = urlparse(cfg.base_url).hostname
        got_host = urlparse(url).hostname
        if not base_host or base_host != got_host:
            raise InsForgeError(
                InsForgeErrorCategory.SECURITY_POLICY_DENIED, "host_mismatch",
            )

        headers = {
            "Accept": "application/json",
            "User-Agent": "SaathiOS-InsForgePilot/m18.4",
        }
        if cfg.api_key:
            if cfg.api_key.startswith("ik_") or cfg.api_key.startswith("anon_"):
                headers["Authorization"] = f"Bearer {cfg.api_key}"
                headers["X-API-Key"] = cfg.api_key
            else:
                headers["Authorization"] = f"Bearer {cfg.api_key}"

        try:
            import httpx
        except ImportError as e:
            raise InsForgeError(
                InsForgeErrorCategory.PROVIDER_UNAVAILABLE, "httpx_missing",
            ) from e

        try:
            with httpx.Client(
                timeout=cfg.timeout_sec,
                transport=self._transport,
                verify=cfg.tls_verify,
                follow_redirects=False,
            ) as client:
                if method_u == "GET":
                    resp = client.get(url, headers=headers, params=params or None)
                else:
                    headers["Content-Type"] = "application/json"
                    resp = client.post(url, headers=headers, json=json_body or {})
        except httpx.TimeoutException as e:
            raise InsForgeError(InsForgeErrorCategory.TIMEOUT, "request_timeout") from e
        except httpx.TransportError as e:
            raise InsForgeError(
                InsForgeErrorCategory.CONNECTION_FAILED, type(e).__name__,
            ) from e
        except Exception as e:
            raise InsForgeError(
                InsForgeErrorCategory.CONNECTION_FAILED, type(e).__name__,
            ) from e

        raw = resp.content or b""
        if len(raw) > cfg.max_response_bytes:
            raise InsForgeError(
                InsForgeErrorCategory.RESPONSE_TOO_LARGE,
                f"bytes={len(raw)} max={cfg.max_response_bytes}",
                status_code=resp.status_code,
            )

        if 300 <= resp.status_code < 400:
            raise InsForgeError(
                InsForgeErrorCategory.SECURITY_POLICY_DENIED,
                f"redirect_denied:{resp.status_code}",
                status_code=resp.status_code,
            )
        if resp.status_code in (401, 403):
            cat = (
                InsForgeErrorCategory.AUTHENTICATION_FAILED
                if resp.status_code == 401
                else InsForgeErrorCategory.PERMISSION_DENIED
            )
            raise InsForgeError(cat, f"http_{resp.status_code}", status_code=resp.status_code)
        if resp.status_code >= 500:
            raise InsForgeError(
                InsForgeErrorCategory.PROVIDER_UNAVAILABLE,
                f"http_{resp.status_code}",
                status_code=resp.status_code,
            )
        if resp.status_code >= 400:
            raise InsForgeError(
                InsForgeErrorCategory.PROVIDER_UNAVAILABLE,
                f"http_{resp.status_code}",
                status_code=resp.status_code,
            )

        if not raw:
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise InsForgeError(
                InsForgeErrorCategory.INVALID_PROVIDER_RESPONSE, "json_decode_failed",
            ) from e

    def reject_write(self, method: str, path: str) -> None:
        raise InsForgeError(
            InsForgeErrorCategory.WRITE_FORBIDDEN,
            f"write_methods_unsupported:{method}:{path[:40]}",
        )
