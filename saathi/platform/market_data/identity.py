"""Canonical market/instrument/venue consistency checks.

``venue`` is the canonical internal concept. Provider-specific exchange names
are accepted only at adapter boundaries and are never used as implicit
defaults.  This module deliberately has no provider, network, or execution
authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class IdentityValidationError(ValueError):
    """Deterministic rejection of an inconsistent financial identity."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True)
class MarketIdentity:
    instrument_id: str | None
    venue: str
    market: str
    asset_class: str


# Venue is intentionally a string boundary, not a second exchange enum.
# These are known consistency facts, not defaults.
_VENUE_FACTS: dict[str, tuple[str, str]] = {
    "NEPSE": ("NEPSE", "EQUITY"),
    "XNAS": ("US", "EQUITY"),
    "XNYS": ("US", "EQUITY"),
    "NYSE_ARCA": ("US", "EQUITY"),
    "BINANCE": ("CRYPTO", "CRYPTO"),
    "CRYPTO": ("CRYPTO", "CRYPTO"),
    "SIM": ("SIM", "UNKNOWN"),
}


def _clean(value: Any) -> str:
    value = getattr(value, "value", value)
    return str(value or "").strip().upper().replace("-", "_")


def resolve_market_identity(
    *,
    instrument_id: str | None = None,
    venue: str | None = None,
    market: str | None = None,
    asset_class: str | None = None,
) -> MarketIdentity:
    """Resolve and validate one canonical identity without silent coercion.

    A venue may be derived from a venue-qualified instrument ID, and NEPSE is
    derived from an explicitly NEPSE market because that contract is
    unambiguous.  Generic missing values remain ``UNKNOWN``.
    """
    raw_instrument = str(instrument_id or "").strip()
    canonical_instrument = raw_instrument
    clean_venue = _clean(venue)
    clean_market = _clean(market)
    clean_asset = _clean(asset_class)

    prefix = ""
    if raw_instrument:
        if ":" in raw_instrument:
            prefix = _clean(raw_instrument.split(":", 1)[0])
            symbol = raw_instrument.split(":", 1)[1].strip().upper()
            if not symbol:
                raise IdentityValidationError("INVALID_INSTRUMENT", "instrument symbol is blank")
            canonical_instrument = f"{prefix}:{symbol}"
            if prefix not in _VENUE_FACTS:
                raise IdentityValidationError("UNKNOWN_VENUE", f"instrument prefix {prefix!r} is not registered")
            if clean_venue and clean_venue != prefix:
                raise IdentityValidationError(
                    "IDENTITY_CONTRADICTION",
                    f"instrument {raw_instrument!r} requires venue {prefix}, got {clean_venue}",
                )
            clean_venue = prefix
        else:
            if raw_instrument.upper() in {"UNKNOWN", "UNSPECIFIED"}:
                raise IdentityValidationError("UNKNOWN_INSTRUMENT", "instrument identity is unspecified")
            if not clean_venue and clean_market == "NEPSE":
                clean_venue = "NEPSE"
                canonical_instrument = f"NEPSE:{raw_instrument.upper()}"
            if not clean_venue:
                raise IdentityValidationError("UNKNOWN_VENUE", "unqualified instrument requires an explicit venue")

    if clean_market == "NEPSE" and not clean_venue:
        clean_venue = "NEPSE"
    if clean_venue and clean_venue not in _VENUE_FACTS and clean_venue != "UNKNOWN":
        raise IdentityValidationError("UNKNOWN_VENUE", f"venue {clean_venue!r} is not registered")

    expected_market, expected_asset = _VENUE_FACTS.get(clean_venue, ("UNKNOWN", "UNKNOWN"))
    if clean_market and expected_market not in ("UNKNOWN", "SIM") and clean_market != expected_market:
        raise IdentityValidationError(
            "IDENTITY_CONTRADICTION",
            f"venue {clean_venue} belongs to market {expected_market}, got {clean_market}",
        )
    asset_mismatch = (
        expected_asset == "CRYPTO" and clean_asset not in ("", "CRYPTO")
    ) or (
        expected_asset == "EQUITY" and clean_asset == "CRYPTO"
    )
    if clean_asset and asset_mismatch:
        raise IdentityValidationError(
            "IDENTITY_CONTRADICTION",
            f"venue {clean_venue} requires asset class {expected_asset}, got {clean_asset}",
        )
    if prefix and clean_market and expected_market not in ("UNKNOWN", "SIM") and clean_market != expected_market:
        raise IdentityValidationError("IDENTITY_CONTRADICTION", "instrument, venue, and market disagree")

    return MarketIdentity(
        instrument_id=canonical_instrument or None,
        venue=clean_venue or "UNKNOWN",
        market=clean_market or expected_market or "UNKNOWN",
        asset_class=clean_asset or expected_asset or "UNKNOWN",
    )
