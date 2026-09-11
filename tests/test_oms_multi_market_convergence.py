"""OMS-MULTI-MARKET-1 — venue-neutral convention convergence (deterministic core).

Proves one OMS contract serves crypto (fractional, 24/7) and NEPSE (whole-share,
board-lot, session-bound) without inflating size or silently reshaping past the
lot rule, while equity/unknown symbols pass through unchanged.
"""
from decimal import Decimal

import pytest

from saathi.platform.tg.paper_simulation.conventions import (
    AssetClass,
    ConventionReason,
    CRYPTO_CONVENTION,
    NEPSE_CONVENTION,
    convention_for,
    normalize_order,
)
from saathi.platform.tg.paper_simulation.calendar import TradingCalendar


# ── routing parity: conventions must agree with the session calendar ─────────────
@pytest.mark.parametrize(
    "symbol,expected",
    [
        ("BTCUSDT", AssetClass.CRYPTO),
        ("ethusdt", AssetClass.CRYPTO),
        ("BTC", AssetClass.CRYPTO),
        ("NEPSE:NABIL", AssetClass.NEPSE_EQUITY),
        ("AAPL", AssetClass.EQUITY),
        ("", AssetClass.EQUITY),
    ],
)
def test_convention_routing(symbol, expected):
    assert convention_for(symbol).asset_class == expected


def test_routing_matches_trading_calendar_asset_class():
    cal = TradingCalendar()
    # crypto
    assert cal.for_symbol("BTCUSDT")["asset_class"] == "crypto"
    assert convention_for("BTCUSDT").is_247 is True
    # nepse is equity-class but session-bound (not 24/7)
    assert cal.for_symbol("NEPSE:NABIL")["is_247"] is False
    assert convention_for("NEPSE:NABIL").is_247 is False


# ── crypto: fractional, step rounding, min-qty, tick ─────────────────────────────
def test_crypto_fractional_accepted_and_rounded_down():
    n = normalize_order("BTCUSDT", 0.123456789, price=42000.017)
    assert n.accepted
    assert n.quantity == Decimal("0.123456")  # rounded DOWN to 1e-6 step
    assert ConventionReason.QTY_ROUNDED_DOWN.value in n.reasons
    assert n.price == Decimal("42000.02")     # to 0.01 tick
    assert ConventionReason.PRICE_ROUNDED_TO_TICK.value in n.reasons


def test_crypto_below_min_rejected():
    n = normalize_order("ETHUSDT", 0.0000004)  # below 1e-6 step and min
    assert not n.accepted
    assert n.reasons[0] in (
        ConventionReason.QTY_ZERO_AFTER_STEP.value,
        ConventionReason.QTY_BELOW_MIN.value,
    )


def test_crypto_exact_step_no_rounding_reason():
    n = normalize_order("BTCUSDT", 0.5, price=42000.0)
    assert n.accepted
    assert n.quantity == Decimal("0.5")
    assert ConventionReason.QTY_ROUNDED_DOWN.value not in n.reasons


# ── NEPSE: whole shares, board lot, reject not reshape ───────────────────────────
def test_nepse_whole_lot_multiple_accepted():
    n = normalize_order("NEPSE:NABIL", 20, price=512.03)
    assert n.accepted
    assert n.quantity == Decimal("20")
    assert n.price == Decimal("512.00")  # to 0.10 tick


def test_nepse_fractional_rejected_not_truncated():
    n = normalize_order("NEPSE:NABIL", 10.5)
    assert not n.accepted
    assert n.reasons == (ConventionReason.QTY_NOT_WHOLE.value,)


def test_nepse_non_lot_multiple_rejected():
    n = normalize_order("NEPSE:NABIL", 15)  # whole but not a multiple of 10
    assert not n.accepted
    assert n.reasons == (ConventionReason.QTY_NOT_LOT_MULTIPLE.value,)


def test_nepse_below_min_rejected():
    n = normalize_order("NEPSE:NABIL", 0)
    assert not n.accepted


# ── equity passthrough: legacy behaviour preserved ───────────────────────────────
def test_equity_passthrough_unchanged():
    n = normalize_order("AAPL", 100.0, price=180.005)
    assert n.accepted
    assert n.quantity == Decimal("100.0")
    assert n.price == Decimal("180.005")  # no tick rounding for passthrough
    assert n.reasons == (ConventionReason.OK.value,)


def test_equity_fractional_allowed_in_passthrough():
    n = normalize_order("SPY", 1.5)
    assert n.accepted
    assert n.quantity == Decimal("1.5")


# ── monotonic safety invariant: normalization never inflates quantity ────────────
@pytest.mark.parametrize("symbol", ["BTCUSDT", "ETHUSDT", "NEPSE:NABIL", "AAPL"])
@pytest.mark.parametrize("q", ["0.9999999", "1", "10", "13.7", "1000.5"])
def test_normalize_never_increases_quantity(symbol, q):
    n = normalize_order(symbol, q)
    if n.accepted:
        assert n.quantity <= Decimal(q), f"{symbol} {q} inflated to {n.quantity}"


def test_profiles_are_frozen_and_typed():
    assert CRYPTO_CONVENTION.allow_fractional is True
    assert NEPSE_CONVENTION.allow_fractional is False
    assert NEPSE_CONVENTION.lot_size == Decimal("10")
    with pytest.raises(Exception):
        CRYPTO_CONVENTION.quantity_step = Decimal("1")  # frozen dataclass
