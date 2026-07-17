"""M27 — Connector policy (allow/deny, domains, operations)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.parse import urlparse

from saathi.connectors.gov.models import ConnectorManifest, ConnectorRequest, FORBIDDEN_PAYLOAD_KEYS


@dataclass
class PolicyDecision:
    allowed: bool
    reason: str = ""
    check_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"allowed": self.allowed, "reason": self.reason, "check_id": self.check_id}


@dataclass
class ConnectorPolicy:
    """Static policy evaluator — fails closed."""

    global_deny_domains: tuple[str, ...] = (
        "metadata.google.internal",
        "169.254.169.254",
    )
    global_deny_operations: tuple[str, ...] = (
        "trade.execute",
        "withdrawal",
        "transfer_funds",
    )
    require_https_for_remote: bool = True
    max_payload_bytes: int = 256_000

    def evaluate(self, manifest: ConnectorManifest, request: ConnectorRequest) -> PolicyDecision:
        if manifest.trading:
            return PolicyDecision(False, "trading_connectors_forbidden", "policy.trading")
        if manifest.cloud and request.operation not in ("health", "validate", "discover"):
            # Cloud SaaS not enabled in M27 for live ops; health/validate ok as dry metadata
            return PolicyDecision(False, "cloud_connectors_disabled_m27", "policy.cloud")

        op = request.operation
        if op in self.global_deny_operations or op in (manifest.denied_operations or ()):
            return PolicyDecision(False, f"operation_denied:{op}", "policy.operation_denied")

        if manifest.allowed_operations and op not in manifest.allowed_operations:
            if op not in (manifest.supported_operations or ()) and op not in (manifest.capabilities or ()):
                return PolicyDecision(False, f"operation_not_allowed:{op}", "policy.operation_allowlist")

        # Supported operations check
        supported = set(manifest.supported_operations or ()) | set(manifest.capabilities or ())
        if supported and op not in supported and op not in ("health", "validate"):
            return PolicyDecision(False, f"unsupported_operation:{op}", "policy.unsupported")

        # Domain restrictions for HTTP-ish requests
        url = (request.url or "").strip()
        if url:
            host = (urlparse(url).hostname or "").lower()
            scheme = (urlparse(url).scheme or "").lower()
            if host in {d.lower() for d in self.global_deny_domains}:
                return PolicyDecision(False, f"domain_denied:{host}", "policy.domain_denied")
            for d in manifest.denied_domains or ():
                if host == d.lower() or host.endswith("." + d.lower()):
                    return PolicyDecision(False, f"domain_denied:{host}", "policy.domain_denied")
            if manifest.allowed_domains:
                ok = any(host == a.lower() or host.endswith("." + a.lower()) for a in manifest.allowed_domains)
                if not ok:
                    return PolicyDecision(False, f"domain_not_allowlisted:{host}", "policy.domain_allowlist")
            if self.require_https_for_remote and scheme and scheme not in ("https", "http"):
                # allow http only for loopback in adapter; policy flags non-http(s)
                if scheme not in ("https", "http"):
                    return PolicyDecision(False, f"scheme_denied:{scheme}", "policy.scheme")
            if self.require_https_for_remote and scheme == "http":
                if host not in ("127.0.0.1", "localhost", "::1"):
                    return PolicyDecision(False, "http_only_allowed_on_loopback", "policy.https")

        # Forbidden payload keys (secrets must not travel in governed payload dict)
        for k in (request.payload or {}):
            if str(k).lower() in FORBIDDEN_PAYLOAD_KEYS:
                return PolicyDecision(False, f"forbidden_payload_key:{k}", "policy.payload_secret")
        for k in (request.headers or {}):
            lk = str(k).lower()
            if lk in FORBIDDEN_PAYLOAD_KEYS or lk in ("authorization", "cookie", "set-cookie", "x-api-key"):
                return PolicyDecision(False, f"forbidden_header:{k}", "policy.header_secret")

        # Size bound
        try:
            import json
            size = len(json.dumps(request.payload or {}, default=str).encode("utf-8"))
            if size > self.max_payload_bytes:
                return PolicyDecision(False, "payload_too_large", "policy.payload_size")
        except Exception:
            return PolicyDecision(False, "payload_unserializable", "policy.payload_schema")

        return PolicyDecision(True, "ok", "policy.pass")
