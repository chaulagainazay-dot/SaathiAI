"""Phase 2 — deterministic source tiering.

An unknown domain is TIER_6_UNKNOWN, never silently authoritative. Only the
explicit official allowlist is TIER_1. Tiering is host-based and fail-closed.
"""
from __future__ import annotations

from enum import IntEnum
from urllib.parse import urlparse


class SourceTier(IntEnum):
    TIER_1_OFFICIAL = 1        # exchange / regulator / central bank / gov / official filing
    TIER_2_PRIMARY_DATA = 2    # recognized market-data provider / official releases
    TIER_3_REPUTABLE_NEWS = 3
    TIER_4_SECONDARY_ANALYSIS = 4
    TIER_5_SOCIAL_COMMUNITY = 5
    TIER_6_UNKNOWN = 6         # default — treat as least authoritative


# NEPSE Tier-1 official allowlist (host suffixes). Kept deliberately small and
# official-only for v1. Company IR pages are added per-symbol by the mission.
NEPSE_TIER1_HOSTS: tuple[str, ...] = (
    "nepalstock.com",          # NEPSE
    "nepalstock.com.np",
    "sebon.gov.np",            # Securities Board of Nepal (SEBON)
    "nrb.org.np",              # Nepal Rastra Bank (NRB, central bank)
    "cdsc.com.np",             # CDS & Clearing
    "cdscnp.com",
    "merolagani.com",          # widely used official-notice mirror (still tier-2 data)
)

# Hosts that are official primary/gov but not the core exchange/regulator set.
NEPSE_TIER1_GOV_SUFFIXES: tuple[str, ...] = (
    ".gov.np",                 # Nepal government
)

# Recognized market-data / primary aggregators (Tier 2).
NEPSE_TIER2_HOSTS: tuple[str, ...] = (
    "nepsealpha.com",
    "sharesansar.com",
)

# Reputable Nepal financial news (Tier 3). Not used in v1 official-only missions
# except as deterministic test fixtures.
NEPSE_TIER3_HOSTS: tuple[str, ...] = (
    "myrepublica.nagariknetwork.com",
    "kathmandupost.com",
    "thehimalayantimes.com",
)


def host_of(url: str) -> str:
    try:
        h = (urlparse(url).hostname or "").lower().strip()
    except Exception:
        return ""
    return h[:-1] if h.endswith(".") else h


def _matches(host: str, roots: tuple[str, ...]) -> bool:
    for r in roots:
        r = r.lower().lstrip(".")
        if host == r or host.endswith("." + r):
            return True
    return False


def _suffix_matches(host: str, suffixes: tuple[str, ...]) -> bool:
    return any(host.endswith(s) for s in suffixes)


def classify_host(host: str) -> SourceTier:
    if not host:
        return SourceTier.TIER_6_UNKNOWN
    host = host.lower().rstrip(".")
    if _matches(host, NEPSE_TIER1_HOSTS) or _suffix_matches(host, NEPSE_TIER1_GOV_SUFFIXES):
        return SourceTier.TIER_1_OFFICIAL
    if _matches(host, NEPSE_TIER2_HOSTS):
        return SourceTier.TIER_2_PRIMARY_DATA
    if _matches(host, NEPSE_TIER3_HOSTS):
        return SourceTier.TIER_3_REPUTABLE_NEWS
    return SourceTier.TIER_6_UNKNOWN


def classify_source(url: str) -> SourceTier:
    return classify_host(host_of(url))


def is_official(url_or_host: str) -> bool:
    host = host_of(url_or_host) or (url_or_host or "").lower().strip()
    return classify_host(host) == SourceTier.TIER_1_OFFICIAL


def tier1_allowlist() -> tuple[str, ...]:
    """Host suffixes to hand GovernedBrowser as its domain allowlist (official-only)."""
    return NEPSE_TIER1_HOSTS + tuple(s.lstrip(".") for s in NEPSE_TIER1_GOV_SUFFIXES)
