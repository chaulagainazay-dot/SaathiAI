"""M33 — DNS resolution + SSRF defense (authoritative destination guard).

Both the configured hostname AND every resolved IP address are validated. Private,
loopback, link-local, multicast, reserved, unspecified, and cloud-metadata
destinations are rejected. Redirects and every fresh DNS resolution are
revalidated. Hostname text is never trusted on its own. Resolution is injectable
so deterministic tests never touch the network. Any ambiguity fails closed.
"""
from __future__ import annotations

import ipaddress
from typing import Callable, Optional

from saathi.connectors.providers.external.models import ExternalFailure

# Cloud metadata endpoints (kept explicit even though link-local covers most).
METADATA_ADDRESSES = frozenset({
    "169.254.169.254",   # AWS / GCP / Azure IMDS
    "100.100.100.200",   # Alibaba Cloud
    "fd00:ec2::254",     # AWS IMDSv2 IPv6
})

# A resolver maps a hostname to a list of IP strings. Injectable for tests.
Resolver = Callable[[str], list[str]]


class DnsSsrfError(ValueError):
    """Raised on DNS/SSRF policy failure. Carries a bounded failure code."""

    def __init__(self, code: ExternalFailure, message: str = ""):
        self.code = code
        super().__init__(f"{code.value}:{message[:80]}")


def classify_address(ip_str: str) -> str:
    """Classify an IP literal. Returns a bounded category string (fail closed to invalid)."""
    s = (ip_str or "").strip()
    if s in METADATA_ADDRESSES:
        return "metadata"
    try:
        ip = ipaddress.ip_address(s)
    except ValueError:
        return "invalid"
    if ip.is_loopback:
        return "loopback"
    if ip.is_link_local:
        return "link_local"
    if ip.is_multicast:
        return "multicast"
    if ip.is_unspecified:
        return "unspecified"
    if ip.is_reserved:
        return "reserved"
    if ip.is_private:
        return "private"
    if getattr(ip, "is_site_local", False):
        return "private"
    if ip.is_global:
        return "public"
    # anything we cannot positively classify as public → fail closed
    return "reserved"


def is_public_address(ip_str: str) -> bool:
    return classify_address(ip_str) == "public"


def default_resolver(host: str) -> list[str]:
    """Real DNS via getaddrinfo — used ONLY on the live path, never in tests."""
    import socket

    out: list[str] = []
    for fam, _, _, _, sockaddr in socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP):
        addr = sockaddr[0]
        if addr and addr not in out:
            out.append(addr)
    return out


def resolve_and_validate(
    host: str,
    *,
    resolver: Optional[Resolver] = None,
) -> list[str]:
    """Resolve ``host`` and validate every address. Returns pinned public IPs.

    Fails closed: empty result, resolver error, or ANY non-public address (mixed
    results included) raises DnsSsrfError. The returned list is the set of IPs the
    transport must connect to (no second resolution → no rebinding window).
    """
    h = (host or "").strip().lower().rstrip(".")
    if not h:
        raise DnsSsrfError(ExternalFailure.DNS_RESOLUTION_FAILED, "empty_host")

    r = resolver or default_resolver
    try:
        addrs = list(r(h) or [])
    except TimeoutError:
        raise DnsSsrfError(ExternalFailure.NETWORK_TIMEOUT, "dns_timeout")
    except Exception as e:  # resolver failure → safe classification, no raw dump
        raise DnsSsrfError(ExternalFailure.DNS_RESOLUTION_FAILED, type(e).__name__)

    if not addrs:
        raise DnsSsrfError(ExternalFailure.DNS_RESOLUTION_FAILED, "no_addresses")

    validated: list[str] = []
    for a in addrs:
        cat = classify_address(a)
        if cat == "metadata":
            raise DnsSsrfError(ExternalFailure.SSRF_POLICY_BLOCKED, "metadata_service")
        if cat != "public":
            # mixed public/private also lands here → fail closed for the whole op
            raise DnsSsrfError(ExternalFailure.SSRF_POLICY_BLOCKED, f"non_public:{cat}")
        validated.append(a)
    return validated
