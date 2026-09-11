"""NEPSE instrument master — canonical identity for Nepali listed securities.

Why this exists
---------------
Every downstream artifact — an imported holding, a portfolio valuation, a
backtest bar, an evidence record — is keyed by instrument. If two spellings of
the same security ("nabil", "NEPSE:NABIL", "NABIL.N") produce two identities,
positions split, valuations disagree, and reconciliation cannot close. Provider
symbols therefore never travel inside SaathiOS; they map through here first.

Scope of this module
--------------------
Identity, sector taxonomy, and NEPSE-appropriate trading conventions. It holds
no prices, performs no network I/O, and has no execution authority. It is a
read-only reference layer that sits upstream of everything.

NEPSE conventions encoded here differ from US and crypto defaults on purpose:
whole-share quantities, a round lot of 10, a 0.10 paisa tick, NPR, and
``Asia/Kathmandu``. Assuming US semantics is the standing failure mode this
module is meant to prevent.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

__all__ = [
    "NEPSE_VENUE",
    "NEPSE_CURRENCY",
    "NEPSE_TIMEZONE",
    "NepseSector",
    "NepseInstrument",
    "normalize_symbol",
    "instrument_id_for",
    "sector_from_code",
]

NEPSE_VENUE = "NEPSE"
NEPSE_CURRENCY = "NPR"
NEPSE_TIMEZONE = "Asia/Kathmandu"

# NEPSE trades whole shares in a round lot of 10, quoted to two decimals with a
# 0.10 minimum tick. These are deliberately explicit rather than inherited from
# a generic equity default.
NEPSE_LOT_SIZE = 10
NEPSE_TICK_SIZE = "0.10"
NEPSE_PRICE_PRECISION = 2
NEPSE_QUANTITY_PRECISION = 0

VALID_STATUSES = frozenset({"ACTIVE", "SUSPENDED", "DELISTED", "PENDING_LISTING"})

# Provider prefixes and suffixes seen in NEPSE exports and third-party feeds.
_VENUE_PREFIX = re.compile(r"^(?:NEPSE|NEP)\s*[:\-]\s*", re.IGNORECASE)
_TRAILING_SUFFIX = re.compile(r"\.(?:N|NP|NEP)$", re.IGNORECASE)
_NON_SYMBOL = re.compile(r"[^A-Z0-9]")


class NepseSector(str, Enum):
    """NEPSE sub-sector taxonomy.

    ``OTHERS`` is a real NEPSE sector and doubles as the fallback for a listing
    whose sector string is not recognised — a new sector must never make an
    instrument unrepresentable.
    """

    COMMERCIAL_BANKS = "COMMERCIAL_BANKS"
    DEVELOPMENT_BANKS = "DEVELOPMENT_BANKS"
    FINANCE = "FINANCE"
    MICROFINANCE = "MICROFINANCE"
    LIFE_INSURANCE = "LIFE_INSURANCE"
    NON_LIFE_INSURANCE = "NON_LIFE_INSURANCE"
    HYDROPOWER = "HYDROPOWER"
    HOTELS_AND_TOURISM = "HOTELS_AND_TOURISM"
    MANUFACTURING_AND_PROCESSING = "MANUFACTURING_AND_PROCESSING"
    TRADING = "TRADING"
    INVESTMENT = "INVESTMENT"
    MUTUAL_FUND = "MUTUAL_FUND"
    CORPORATE_DEBENTURE = "CORPORATE_DEBENTURE"
    PREFERRED_STOCK = "PREFERRED_STOCK"
    OTHERS = "OTHERS"


# Spellings observed across NEPSE disclosures and third-party exports.
_SECTOR_ALIASES: dict[str, NepseSector] = {
    "COMMERCIALBANKS": NepseSector.COMMERCIAL_BANKS,
    "COMMERCIALBANK": NepseSector.COMMERCIAL_BANKS,
    "BANKING": NepseSector.COMMERCIAL_BANKS,
    "DEVELOPMENTBANKS": NepseSector.DEVELOPMENT_BANKS,
    "DEVELOPMENTBANK": NepseSector.DEVELOPMENT_BANKS,
    "FINANCE": NepseSector.FINANCE,
    "FINANCECOMPANY": NepseSector.FINANCE,
    "MICROFINANCE": NepseSector.MICROFINANCE,
    "MICROFINANCEINSTITUTION": NepseSector.MICROFINANCE,
    "MICROFINANCEINSTITUTIONS": NepseSector.MICROFINANCE,
    "LIFEINSURANCE": NepseSector.LIFE_INSURANCE,
    "NONLIFEINSURANCE": NepseSector.NON_LIFE_INSURANCE,
    "INSURANCE": NepseSector.NON_LIFE_INSURANCE,
    "HYDROPOWER": NepseSector.HYDROPOWER,
    "HYDRO": NepseSector.HYDROPOWER,
    "HOTELSANDTOURISM": NepseSector.HOTELS_AND_TOURISM,
    "HOTELS": NepseSector.HOTELS_AND_TOURISM,
    "HOTELTOURISM": NepseSector.HOTELS_AND_TOURISM,
    "MANUFACTURINGANDPROCESSING": NepseSector.MANUFACTURING_AND_PROCESSING,
    "MANUFACTURING": NepseSector.MANUFACTURING_AND_PROCESSING,
    "TRADING": NepseSector.TRADING,
    "TRADINGS": NepseSector.TRADING,
    "INVESTMENT": NepseSector.INVESTMENT,
    "MUTUALFUND": NepseSector.MUTUAL_FUND,
    "MUTUALFUNDS": NepseSector.MUTUAL_FUND,
    "CORPORATEDEBENTURE": NepseSector.CORPORATE_DEBENTURE,
    "DEBENTURE": NepseSector.CORPORATE_DEBENTURE,
    "PREFERREDSTOCK": NepseSector.PREFERRED_STOCK,
    "PREFERENCESHARE": NepseSector.PREFERRED_STOCK,
    "OTHERS": NepseSector.OTHERS,
    "OTHER": NepseSector.OTHERS,
}


def normalize_symbol(symbol: Any) -> str:
    """Canonical NEPSE ticker.

    Strips venue prefixes, trailing venue suffixes, internal whitespace and
    punctuation, and upper-cases. Raises rather than returning a guess: a
    symbol that cannot be parsed must not silently become a different, real
    security.
    """
    if not isinstance(symbol, str):
        raise TypeError(f"symbol must be a string, got {type(symbol).__name__}")
    s = _VENUE_PREFIX.sub("", symbol.strip()).strip()
    s = _TRAILING_SUFFIX.sub("", s)
    s = _NON_SYMBOL.sub("", s.upper())
    if not s:
        raise ValueError(f"unusable NEPSE symbol: {symbol!r}")
    return s


def instrument_id_for(symbol: Any) -> str:
    """Venue-qualified identity. Keeps NEPSE and crypto identities disjoint."""
    return f"{NEPSE_VENUE}:{normalize_symbol(symbol)}"


def sector_from_code(code: Any) -> NepseSector:
    """Map a provider sector string to the taxonomy. Unknown maps to OTHERS."""
    if not isinstance(code, str):
        return NepseSector.OTHERS
    key = _NON_SYMBOL.sub("", code.upper())
    if not key:
        return NepseSector.OTHERS
    try:
        return NepseSector(key)
    except ValueError:
        pass
    return _SECTOR_ALIASES.get(key, NepseSector.OTHERS)


@dataclass(frozen=True)
class NepseInstrument:
    """One listed NEPSE security. Reference data only — no prices, no state."""

    instrument_id: str
    symbol: str
    name: str
    sector: NepseSector
    venue: str = NEPSE_VENUE
    currency: str = NEPSE_CURRENCY
    asset_class: str = "EQUITY"
    listed_shares: str = "0"
    paid_up_value: str = "100"
    lot_size: int = NEPSE_LOT_SIZE
    tick_size: str = NEPSE_TICK_SIZE
    price_precision: int = NEPSE_PRICE_PRECISION
    quantity_precision: int = NEPSE_QUANTITY_PRECISION
    timezone: str = NEPSE_TIMEZONE
    trading_calendar: str = "NEPSE"
    status: str = "ACTIVE"
    isin: str = ""
    company_id: str = ""
    source: str = ""
    as_of: str = ""
    aliases: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def create(
        cls,
        *,
        symbol: str,
        name: str,
        sector: NepseSector | str,
        **kwargs: Any,
    ) -> "NepseInstrument":
        clean_name = (name or "").strip()
        if not clean_name:
            raise ValueError("instrument name must not be blank")

        status = str(kwargs.pop("status", "ACTIVE")).upper()
        if status not in VALID_STATUSES:
            raise ValueError(
                f"invalid status {status!r}; expected one of {sorted(VALID_STATUSES)}"
            )

        canonical = normalize_symbol(symbol)
        resolved_sector = (
            sector if isinstance(sector, NepseSector) else sector_from_code(sector)
        )
        return cls(
            instrument_id=f"{NEPSE_VENUE}:{canonical}",
            symbol=canonical,
            name=clean_name,
            sector=resolved_sector,
            status=status,
            **kwargs,
        )

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["sector"] = self.sector.value
        d["aliases"] = list(self.aliases)
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NepseInstrument":
        d = dict(data)
        d["sector"] = NepseSector(d["sector"]) if not isinstance(d.get("sector"), NepseSector) else d["sector"]
        d["aliases"] = tuple(d.get("aliases") or ())
        return cls(**d)
