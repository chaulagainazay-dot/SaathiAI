"""M33 — Strict external endpoint policy (fail closed).

External execution is HTTPS-only, against a canonical hostname allowlist and port
policy declared in the provider profile. Callers can never supply an endpoint,
host, port, proxy, DNS override, or TLS setting. Redirect targets are revalidated
against the same policy. The M32 loopback/in-process simulator keeps its own
separate classification and is never widened by this policy (and vice versa).
"""
from __future__ import annotations

from typing import Any, Optional
from urllib.parse import urlparse

from saathi.connectors.providers.external.models import (
    EndpointClass,
    ExternalFailure,
    ExternalProviderProfile,
)

# Schemes that are always blocked for external providers.
BLOCKED_SCHEMES = frozenset({
    "http", "ftp", "gopher", "file", "data", "javascript", "ws", "wss",
    "ldap", "dict", "tftp", "unix", "ssh", "smtp",
})

# Hostnames that must never be an external destination (defense-in-depth; the
# resolved-IP SSRF check in dns_ssrf.py is the authoritative guard).
BLOCKED_HOST_LITERALS = frozenset({
    "localhost", "127.0.0.1", "0.0.0.0", "::1", "loopback", "metadata",
    "metadata.google.internal", "169.254.169.254", "instance-data",
})

# Caller metadata keys that must never influence the destination.
CALLER_FORBIDDEN_ENDPOINT_KEYS = frozenset({
    "endpoint", "endpoint_reference", "url", "base_url", "host", "hostname",
    "port", "proxy", "proxies", "http_proxy", "https_proxy", "no_proxy",
    "dns", "resolver", "ip", "address", "sni", "tls", "verify", "ca_bundle",
    "scheme", "netloc",
})


class EndpointPolicyError(ValueError):
    """Raised when an endpoint fails the external policy. Carries a failure code."""

    def __init__(self, code: ExternalFailure, message: str = ""):
        self.code = code
        super().__init__(f"{code.value}:{message}")


def caller_attempts_endpoint_override(metadata: Optional[dict[str, Any]]) -> Optional[str]:
    """Return the offending key if caller metadata tries to steer the destination."""
    if not metadata:
        return None
    for k in metadata:
        if str(k).lower() in CALLER_FORBIDDEN_ENDPOINT_KEYS:
            return str(k).lower()
    return None


def _is_wildcard(host: str) -> bool:
    return "*" in host or host.startswith(".")


def hostname_allowed(host: str, profile: ExternalProviderProfile) -> bool:
    h = (host or "").strip().lower().rstrip(".")
    if not h or _is_wildcard(h):
        return False
    if h in BLOCKED_HOST_LITERALS:
        return False
    allow = {a.strip().lower().rstrip(".") for a in profile.hostname_allowlist}
    # exact match only — no suffix/wildcard widening
    return h in allow


def validate_endpoint(
    url: str,
    profile: ExternalProviderProfile,
    *,
    is_redirect: bool = False,
) -> tuple[str, int, str]:
    """Validate a URL against the profile's external policy.

    Returns ``(host, port, path)`` on success, else raises EndpointPolicyError.
    Used both for the configured endpoint and for every redirect target.
    """
    ep = (url or "").strip()
    if not ep:
        raise EndpointPolicyError(ExternalFailure.ENDPOINT_POLICY_BLOCKED, "endpoint_required")

    if profile.endpoint_class != EndpointClass.HTTPS_EXTERNAL.value:
        raise EndpointPolicyError(ExternalFailure.ENDPOINT_POLICY_BLOCKED, "not_external_profile")

    parsed = urlparse(ep)
    scheme = (parsed.scheme or "").lower()

    if scheme != "https":
        if scheme in BLOCKED_SCHEMES:
            reason = "https_downgrade" if scheme == "http" else f"scheme_blocked:{scheme}"
            raise EndpointPolicyError(ExternalFailure.ENDPOINT_POLICY_BLOCKED, reason)
        raise EndpointPolicyError(ExternalFailure.ENDPOINT_POLICY_BLOCKED, f"scheme_not_https:{scheme or 'none'}")

    # no embedded credentials / userinfo
    if parsed.username or parsed.password or "@" in (parsed.netloc or ""):
        raise EndpointPolicyError(ExternalFailure.ENDPOINT_POLICY_BLOCKED, "userinfo_forbidden")

    host = (parsed.hostname or "").lower().rstrip(".")
    if not host:
        raise EndpointPolicyError(ExternalFailure.ENDPOINT_POLICY_BLOCKED, "host_required")
    if _is_wildcard(host):
        raise EndpointPolicyError(ExternalFailure.ENDPOINT_POLICY_BLOCKED, "wildcard_host_forbidden")
    if host in BLOCKED_HOST_LITERALS:
        raise EndpointPolicyError(ExternalFailure.SSRF_POLICY_BLOCKED, f"blocked_host_literal:{host}")
    if not hostname_allowed(host, profile):
        raise EndpointPolicyError(ExternalFailure.ENDPOINT_POLICY_BLOCKED, f"host_not_allowlisted:{host}")

    try:
        port = parsed.port if parsed.port is not None else 443
    except ValueError:
        raise EndpointPolicyError(ExternalFailure.ENDPOINT_POLICY_BLOCKED, "invalid_port")
    if int(port) not in {int(p) for p in profile.allowed_ports}:
        raise EndpointPolicyError(ExternalFailure.ENDPOINT_POLICY_BLOCKED, f"port_not_allowed:{port}")

    path = parsed.path or "/"
    # for the configured endpoint the path must match the canonical path exactly
    if not is_redirect and path.rstrip("/") != (profile.canonical_path or "/").rstrip("/"):
        raise EndpointPolicyError(ExternalFailure.ENDPOINT_POLICY_BLOCKED, "path_mismatch")
    return host, int(port), path


def validate_redirect_target(url: str, profile: ExternalProviderProfile) -> tuple[str, int, str]:
    """Redirect targets get the same full endpoint policy (revalidated host/scheme/port)."""
    return validate_endpoint(url, profile, is_redirect=True)
