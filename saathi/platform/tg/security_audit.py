"""SECURITY-1 — market-data egress guard and external-text inertness.

Two surfaces the trading program must never get wrong:

1. EGRESS / SSRF. Market data may only be fetched from an explicit allowlist of
   public hosts over HTTPS. Loopback, link-local, cloud-metadata and private ranges
   are refused, credentials embedded in a URL are refused, and PRIVATE/account/order/
   withdrawal paths are refused even on an otherwise allowed host — the program has
   no private account access by design.

2. EXTERNAL TEXT. Provider, research, and imported-file text is DATA. It is carried
   as UNTRUSTED_EXTERNAL_DATA with is_instruction=False (see research.evidence) and
   is never promoted to an instruction. This module provides the assertion used to
   prove that at boundaries.

Deterministic and offline: nothing here performs a request; it decides whether one
would be permitted.
"""
from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from urllib.parse import urlparse

from saathi.platform.research.evidence import EvidenceTrustClass


# Public, read-only market-data hosts actually used by the program.
ALLOWED_MARKET_DATA_HOSTS = frozenset({
    "data.binance.vision",   # official public historical archives
    "api.binance.com",       # public REST (public endpoints only)
    "stream.binance.com",    # public websocket market streams
})

# Path fragments that indicate a private/account/trading endpoint. Refused always.
PRIVATE_PATH_MARKERS = (
    "/api/v3/order", "/api/v3/account", "/api/v3/openorders",
    "/sapi/", "/userdatastream", "/withdraw", "/capital/",
    "/margin", "/futures", "/fapi/", "/dapi/",
)

_BLOCKED_HOSTNAMES = {"localhost", "metadata.google.internal", "instance-data"}


@dataclass(frozen=True)
class EgressDecision:
    allowed: bool
    reason: str
    host: str = ""

    def __bool__(self) -> bool:  # allow `if check_egress(url):`
        return self.allowed


def _is_blocked_ip(host: str) -> bool:
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return (
        ip.is_loopback or ip.is_private or ip.is_link_local
        or ip.is_reserved or ip.is_multicast or ip.is_unspecified
    )


def check_egress(url: str) -> EgressDecision:
    """Decide whether a market-data fetch to `url` is permitted."""
    try:
        parsed = urlparse(str(url))
    except Exception:
        return EgressDecision(False, "URL_UNPARSEABLE")

    if parsed.scheme != "https":
        return EgressDecision(False, "SCHEME_NOT_HTTPS")

    # Credentials must never travel in a URL.
    if parsed.username or parsed.password or "@" in (parsed.netloc.split("/")[0]):
        return EgressDecision(False, "CREDENTIALS_IN_URL")

    host = (parsed.hostname or "").lower()
    if not host:
        return EgressDecision(False, "HOST_MISSING")
    if host in _BLOCKED_HOSTNAMES:
        return EgressDecision(False, "BLOCKED_HOSTNAME", host)
    if _is_blocked_ip(host):
        return EgressDecision(False, "BLOCKED_IP_RANGE", host)
    if host not in ALLOWED_MARKET_DATA_HOSTS:
        return EgressDecision(False, "HOST_NOT_ALLOWLISTED", host)

    path = (parsed.path or "").lower()
    if any(marker in path for marker in PRIVATE_PATH_MARKERS):
        return EgressDecision(False, "PRIVATE_ENDPOINT_REFUSED", host)

    return EgressDecision(True, "OK", host)


def assert_external_text_is_inert(evidence) -> bool:
    """External text must be untrusted data, never an instruction."""
    trust = getattr(evidence, "trust_class", None)
    is_instruction = getattr(evidence, "is_instruction", None)
    return (
        trust == EvidenceTrustClass.UNTRUSTED_EXTERNAL_DATA
        and is_instruction is False
    )


def audit() -> dict:
    """Static security posture for the trading egress surface."""
    return {
        "allowed_market_data_hosts": sorted(ALLOWED_MARKET_DATA_HOSTS),
        "https_only": True,
        "private_account_access": False,
        "order_endpoints_reachable": False,
        "withdrawal_capable": False,
        "credentials_in_url_permitted": False,
        "ssrf_ranges_blocked": ["loopback", "private", "link_local", "reserved", "multicast"],
        "external_text_trust_class": EvidenceTrustClass.UNTRUSTED_EXTERNAL_DATA.value,
        "external_text_is_instruction": False,
    }
