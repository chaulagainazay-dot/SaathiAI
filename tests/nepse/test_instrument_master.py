"""NEPSE-1 — instrument master and sector taxonomy invariants.

Written before the implementation. The rules under test exist because a NEPSE
instrument identity that is not deterministic makes every downstream artifact —
holdings, portfolio value, backtest, evidence record — unreconcilable.
"""
from __future__ import annotations

import pytest

from saathi.platform.nepse import (
    NEPSE_VENUE,
    NepseInstrument,
    NepseSector,
    instrument_id_for,
    normalize_symbol,
    sector_from_code,
)


# ── symbol normalisation ───────────────────────────────────────────────────

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("nabil", "NABIL"),
        ("  NABIL  ", "NABIL"),
        ("NEPSE:NABIL", "NABIL"),
        ("nabil.n", "NABIL"),
        ("N A B I L", "NABIL"),
        ("Nabil\t", "NABIL"),
    ],
)
def test_symbol_normalisation_is_canonical(raw, expected):
    assert normalize_symbol(raw) == expected


def test_symbol_normalisation_is_idempotent():
    once = normalize_symbol(" nepse:nabil.n ")
    assert normalize_symbol(once) == once


@pytest.mark.parametrize("bad", ["", "   ", None, "NEPSE:", "..."])
def test_unusable_symbol_is_rejected_not_guessed(bad):
    """An unparseable symbol must raise, never silently become a real ticker."""
    with pytest.raises((ValueError, TypeError)):
        normalize_symbol(bad)


# ── instrument identity ────────────────────────────────────────────────────

def test_instrument_id_is_venue_qualified():
    assert instrument_id_for("NABIL") == "NEPSE:NABIL"


def test_instrument_id_is_deterministic():
    assert instrument_id_for("nabil") == instrument_id_for(" NEPSE:NABIL ")


def test_instrument_id_never_collides_with_a_crypto_pair():
    """Venue qualification is what keeps NEPSE and crypto identities disjoint."""
    assert instrument_id_for("BTC").startswith("NEPSE:")
    assert instrument_id_for("BTC") != "BINANCE:BTCUSDT"


# ── sector taxonomy ────────────────────────────────────────────────────────

def test_every_sector_has_a_stable_code():
    codes = [s.value for s in NepseSector]
    assert len(codes) == len(set(codes)), "sector codes must be unique"
    assert all(c.isupper() and " " not in c for c in codes)


def test_known_nepse_sectors_are_present():
    present = {s.value for s in NepseSector}
    for expected in (
        "COMMERCIAL_BANKS",
        "DEVELOPMENT_BANKS",
        "FINANCE",
        "MICROFINANCE",
        "LIFE_INSURANCE",
        "NON_LIFE_INSURANCE",
        "HYDROPOWER",
        "HOTELS_AND_TOURISM",
        "MANUFACTURING_AND_PROCESSING",
        "TRADING",
        "INVESTMENT",
        "MUTUAL_FUND",
        "OTHERS",
    ):
        assert expected in present, f"missing NEPSE sector {expected}"


def test_unknown_sector_maps_to_others_not_an_exception():
    """A new listing in an unrecognised sector must still be representable."""
    assert sector_from_code("something-new") is NepseSector.OTHERS


def test_sector_lookup_is_case_and_separator_insensitive():
    assert sector_from_code("commercial banks") is NepseSector.COMMERCIAL_BANKS
    assert sector_from_code("Commercial-Banks") is NepseSector.COMMERCIAL_BANKS
    assert sector_from_code("COMMERCIAL_BANKS") is NepseSector.COMMERCIAL_BANKS


# ── instrument record ──────────────────────────────────────────────────────

def _inst(**over):
    base = dict(
        symbol="NABIL",
        name="Nabil Bank Limited",
        sector=NepseSector.COMMERCIAL_BANKS,
        listed_shares="1000000",
    )
    base.update(over)
    return NepseInstrument.create(**base)


def test_instrument_carries_venue_and_currency():
    inst = _inst()
    assert inst.venue == NEPSE_VENUE
    assert inst.currency == "NPR"
    assert inst.instrument_id == "NEPSE:NABIL"


def test_instrument_is_immutable():
    inst = _inst()
    with pytest.raises((AttributeError, TypeError)):
        inst.symbol = "OTHER"


def test_instrument_defaults_are_nepse_appropriate():
    """NEPSE trades in whole units at 0.10 tick — not US or crypto defaults."""
    inst = _inst()
    assert inst.lot_size == 10          # NEPSE round lot
    assert inst.tick_size == "0.10"
    assert inst.price_precision == 2
    assert inst.quantity_precision == 0  # whole shares only
    assert inst.timezone == "Asia/Kathmandu"
    assert inst.trading_calendar == "NEPSE"


def test_instrument_rejects_a_blank_name():
    with pytest.raises(ValueError):
        _inst(name="  ")


def test_instrument_round_trips_through_dict():
    inst = _inst()
    restored = NepseInstrument.from_dict(inst.to_dict())
    assert restored == inst


def test_instrument_status_defaults_to_active_and_is_constrained():
    assert _inst().status == "ACTIVE"
    with pytest.raises(ValueError):
        _inst(status="whatever")


# ── the authority boundary ─────────────────────────────────────────────────

def test_instrument_master_exposes_no_execution_verb():
    import saathi.platform.nepse as pkg

    forbidden = {"submit", "execute", "approve", "authorize", "place_order", "trade", "buy", "sell"}
    assert not (set(dir(pkg)) & forbidden)


def test_instrument_master_has_no_network_dependency():
    import pathlib

    import saathi.platform.nepse.instruments as m

    src = pathlib.Path(m.__file__).read_text(encoding="utf-8")
    for forbidden in ("requests", "httpx", "urllib", "socket", "aiohttp"):
        assert forbidden not in src, f"network surface in instrument master: {forbidden}"
