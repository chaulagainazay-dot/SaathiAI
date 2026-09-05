"""MD-1 — canonical point-in-time market data contract.

Written before the implementation.

The defect this milestone closes: SaathiOS is ``as_of``-only. A backtest that
filters on ``as_of <= decision_time`` sees a quarterly result the moment the
quarter ends, weeks before it was published. That is the look-ahead defect
recorded in docs/evaluations/tradingagents/LOOKAHEAD_AUDIT.md as a thing to
avoid, and it is currently unfixed here.

The invariant under test is therefore ``available_at <= decision_time``, and the
central case is the one where the two answers differ.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from saathi.platform.market_data.contract import (
    AssetClass,
    CanonicalBar,
    CanonicalQuote,
    CanonicalTrade,
    DataAvailability,
    MarketDataSnapshot,
    MarketStatus,
    PointInTime,
    ProviderReference,
    asset_class_from_legacy,
    visible_at,
)
from saathi.platform.trading_models import DataQuality


def _utc(y, m, d, hh=0, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=timezone.utc)


def _pit(as_of, available_at, received_at=None, event_timestamp=None):
    return PointInTime(
        event_timestamp=event_timestamp or as_of,
        as_of=as_of,
        available_at=available_at,
        received_at=received_at or available_at,
    )


def _provider(name="testprov", event_id="e1", sequence=1):
    return ProviderReference(provider=name, provider_event_id=event_id, sequence=sequence)


def _quote(as_of, available_at, symbol="NEPSE:NABIL"):
    return CanonicalQuote(
        instrument_id=symbol,
        venue="NEPSE",
        asset_class=AssetClass.EQUITY,
        currency="NPR",
        point_in_time=_pit(as_of, available_at),
        provider=_provider(),
        bid=Decimal("534.00"),
        ask=Decimal("536.00"),
        last=Decimal("535.00"),
    )


# ══════════════════════════════════════════════════════════════════════════
# The invariant this milestone exists for
# ══════════════════════════════════════════════════════════════════════════

def test_data_published_after_the_decision_is_not_visible_even_though_its_period_ended_before():
    """The whole point of MD-1.

    A quarter ends 31 March. The filing is published 15 May. A decision taken on
    10 April must NOT see it — even though as_of (31 March) precedes the
    decision. Filtering on as_of alone is the look-ahead bug.
    """
    quarter_end = _utc(2026, 3, 31)
    published = _utc(2026, 5, 15)
    decision = _utc(2026, 4, 10)

    event = _quote(as_of=quarter_end, available_at=published)

    assert event.point_in_time.as_of < decision, "precondition: period ended first"
    assert visible_at([event], decision) == []


def test_the_same_event_becomes_visible_once_publication_has_happened():
    event = _quote(as_of=_utc(2026, 3, 31), available_at=_utc(2026, 5, 15))
    assert visible_at([event], _utc(2026, 5, 15)) == [event]
    assert visible_at([event], _utc(2026, 6, 1)) == [event]


def test_as_of_alone_would_have_admitted_it_and_that_is_the_bug():
    """Documents the wrong filter next to the right one so the difference is
    impossible to miss when someone edits this later."""
    event = _quote(as_of=_utc(2026, 3, 31), available_at=_utc(2026, 5, 15))
    decision = _utc(2026, 4, 10)

    wrong = [e for e in [event] if e.point_in_time.as_of <= decision]
    right = visible_at([event], decision)

    assert wrong == [event], "as_of-only admits it"
    assert right == [], "available_at correctly refuses it"


def test_visibility_boundary_is_inclusive_at_the_publication_instant():
    published = _utc(2026, 5, 15, 10, 0)
    event = _quote(as_of=_utc(2026, 3, 31), available_at=published)
    assert visible_at([event], published) == [event]
    assert visible_at([event], published - timedelta(microseconds=1)) == []


def test_visible_at_preserves_order_and_filters_only():
    a = _quote(_utc(2026, 1, 1), _utc(2026, 1, 1), "NEPSE:AAA")
    b = _quote(_utc(2026, 1, 2), _utc(2026, 9, 1), "NEPSE:BBB")   # not yet published
    c = _quote(_utc(2026, 1, 3), _utc(2026, 1, 3), "NEPSE:CCC")
    out = visible_at([a, b, c], _utc(2026, 2, 1))
    assert [e.instrument_id for e in out] == ["NEPSE:AAA", "NEPSE:CCC"]


def test_visible_at_rejects_a_naive_decision_time():
    """A naive datetime silently compares wrong across timezones. Fail closed."""
    event = _quote(_utc(2026, 1, 1), _utc(2026, 1, 1))
    with pytest.raises(ValueError):
        visible_at([event], datetime(2026, 2, 1))


# ══════════════════════════════════════════════════════════════════════════
# PointInTime
# ══════════════════════════════════════════════════════════════════════════

def test_all_four_timestamps_are_required_and_timezone_aware():
    pit = _pit(_utc(2026, 1, 1), _utc(2026, 1, 2))
    for name in ("event_timestamp", "as_of", "available_at", "received_at"):
        value = getattr(pit, name)
        assert value.tzinfo is not None, f"{name} must be timezone-aware"


@pytest.mark.parametrize("field_name", ["event_timestamp", "as_of", "available_at", "received_at"])
def test_a_naive_timestamp_is_rejected(field_name):
    kwargs = {
        "event_timestamp": _utc(2026, 1, 1),
        "as_of": _utc(2026, 1, 1),
        "available_at": _utc(2026, 1, 1),
        "received_at": _utc(2026, 1, 1),
    }
    kwargs[field_name] = datetime(2026, 1, 1)
    with pytest.raises(ValueError):
        PointInTime(**kwargs)


def test_available_at_before_as_of_is_rejected():
    """Knowing something before the period it describes has ended is impossible."""
    with pytest.raises(ValueError):
        PointInTime(
            event_timestamp=_utc(2026, 3, 31),
            as_of=_utc(2026, 3, 31),
            available_at=_utc(2026, 3, 30),
            received_at=_utc(2026, 3, 30),
        )


def test_received_before_available_is_rejected():
    with pytest.raises(ValueError):
        PointInTime(
            event_timestamp=_utc(2026, 1, 1),
            as_of=_utc(2026, 1, 1),
            available_at=_utc(2026, 1, 5),
            received_at=_utc(2026, 1, 2),
        )


def test_point_in_time_is_immutable():
    pit = _pit(_utc(2026, 1, 1), _utc(2026, 1, 1))
    with pytest.raises((AttributeError, TypeError)):
        pit.available_at = _utc(2027, 1, 1)


def test_publication_lag_is_derivable():
    pit = _pit(_utc(2026, 3, 31), _utc(2026, 5, 15))
    assert pit.publication_lag == timedelta(days=45)


def test_live_data_has_zero_publication_lag():
    t = _utc(2026, 5, 15, 10, 0)
    assert _pit(t, t).publication_lag == timedelta(0)


# ══════════════════════════════════════════════════════════════════════════
# Canonical asset class — convergence, not a fifth enum
# ══════════════════════════════════════════════════════════════════════════

def test_canonical_asset_class_values_are_upper_snake():
    for member in AssetClass:
        assert member.value.isupper()
        assert " " not in member.value


@pytest.mark.parametrize(
    "legacy,expected",
    [
        ("EQUITY", AssetClass.EQUITY),
        ("equity", AssetClass.EQUITY),
        ("CRYPTO", AssetClass.CRYPTO),
        ("crypto", AssetClass.CRYPTO),
        ("ETF", AssetClass.ETF),
        ("etf", AssetClass.ETF),
        ("index", AssetClass.INDEX),
        ("fx", AssetClass.FX),
        ("futures", AssetClass.FUTURES),
        ("OPTIONS", AssetClass.OPTIONS),
        ("CASH", AssetClass.CASH),
    ],
)
def test_every_legacy_asset_class_spelling_converges(legacy, expected):
    """Four AssetClass enums exist in the tree with different casing and members.
    They are adapted, not deleted — ripping them out would break consumers this
    milestone has no mandate to touch."""
    assert asset_class_from_legacy(legacy) is expected


def test_an_unmappable_asset_class_is_rejected_not_defaulted():
    """Silently defaulting an unknown asset class to EQUITY would misclassify an
    instrument in risk and construction."""
    with pytest.raises(ValueError):
        asset_class_from_legacy("dogecoin-perpetual-inverse")


# ══════════════════════════════════════════════════════════════════════════
# Event shapes
# ══════════════════════════════════════════════════════════════════════════

def test_quote_carries_full_identity_and_provenance():
    q = _quote(_utc(2026, 1, 1), _utc(2026, 1, 1))
    assert q.instrument_id == "NEPSE:NABIL"
    assert q.venue == "NEPSE"
    assert q.currency == "NPR"
    assert q.asset_class is AssetClass.EQUITY
    assert q.provider.provider == "testprov"
    assert q.event_type == "QUOTE"
    assert q.quality is DataQuality.UNVERIFIED


def test_quote_spread_and_mid_are_derived_not_stored():
    q = _quote(_utc(2026, 1, 1), _utc(2026, 1, 1))
    assert q.spread == Decimal("2.00")
    assert q.mid == Decimal("535.00")


def test_a_crossed_quote_is_rejected():
    with pytest.raises(ValueError):
        CanonicalQuote(
            instrument_id="NEPSE:NABIL", venue="NEPSE", asset_class=AssetClass.EQUITY,
            currency="NPR", point_in_time=_pit(_utc(2026, 1, 1), _utc(2026, 1, 1)),
            provider=_provider(), bid=Decimal("536"), ask=Decimal("534"), last=Decimal("535"),
        )


def test_a_negative_price_is_rejected():
    with pytest.raises(ValueError):
        CanonicalQuote(
            instrument_id="NEPSE:NABIL", venue="NEPSE", asset_class=AssetClass.EQUITY,
            currency="NPR", point_in_time=_pit(_utc(2026, 1, 1), _utc(2026, 1, 1)),
            provider=_provider(), bid=Decimal("-1"), ask=Decimal("534"), last=Decimal("535"),
        )


def test_bar_rejects_impossible_ohlc():
    with pytest.raises(ValueError):
        CanonicalBar(
            instrument_id="NEPSE:NABIL", venue="NEPSE", asset_class=AssetClass.EQUITY,
            currency="NPR", point_in_time=_pit(_utc(2026, 1, 1), _utc(2026, 1, 2)),
            provider=_provider(),
            open=Decimal("100"), high=Decimal("90"), low=Decimal("95"),
            close=Decimal("98"), volume=Decimal("1000"),
        )


def test_bar_accepts_a_valid_ohlc():
    bar = CanonicalBar(
        instrument_id="NEPSE:NABIL", venue="NEPSE", asset_class=AssetClass.EQUITY,
        currency="NPR", point_in_time=_pit(_utc(2026, 1, 1), _utc(2026, 1, 2)),
        provider=_provider(),
        open=Decimal("100"), high=Decimal("110"), low=Decimal("95"),
        close=Decimal("98"), volume=Decimal("1000"),
    )
    assert bar.event_type == "BAR"


def test_trade_rejects_non_positive_quantity():
    with pytest.raises(ValueError):
        CanonicalTrade(
            instrument_id="NEPSE:NABIL", venue="NEPSE", asset_class=AssetClass.EQUITY,
            currency="NPR", point_in_time=_pit(_utc(2026, 1, 1), _utc(2026, 1, 1)),
            provider=_provider(), price=Decimal("535"), quantity=Decimal("0"),
        )


def test_events_are_immutable():
    q = _quote(_utc(2026, 1, 1), _utc(2026, 1, 1))
    with pytest.raises((AttributeError, TypeError)):
        q.last = Decimal("999")


def test_every_event_round_trips_through_dict():
    q = _quote(_utc(2026, 1, 1), _utc(2026, 1, 1))
    d = q.to_dict()
    assert d["event_type"] == "QUOTE"
    assert d["point_in_time"]["available_at"]
    assert d["provider"]["provider"] == "testprov"


# ══════════════════════════════════════════════════════════════════════════
# Market status and snapshot
# ══════════════════════════════════════════════════════════════════════════

def test_market_status_values_are_explicit():
    assert {m.value for m in MarketStatus} >= {
        "PRE_OPEN", "OPEN", "CLOSED", "HALTED", "UNKNOWN",
    }


def test_unknown_market_status_is_available_and_is_the_safe_default():
    assert MarketStatus.UNKNOWN.value == "UNKNOWN"


def test_snapshot_filters_its_own_events_by_availability():
    published_later = _quote(_utc(2026, 1, 1), _utc(2026, 9, 1), "NEPSE:LATE")
    already_public = _quote(_utc(2026, 1, 1), _utc(2026, 1, 1), "NEPSE:NOW")
    snap = MarketDataSnapshot(
        decision_time=_utc(2026, 2, 1),
        events=(published_later, already_public),
        market_status=MarketStatus.CLOSED,
    )
    assert [e.instrument_id for e in snap.visible_events] == ["NEPSE:NOW"]


def test_snapshot_rejects_a_naive_decision_time():
    with pytest.raises(ValueError):
        MarketDataSnapshot(decision_time=datetime(2026, 2, 1), events=(), market_status=MarketStatus.CLOSED)


def test_availability_states_are_explicit():
    assert {a.value for a in DataAvailability} >= {"AVAILABLE", "NOT_YET_AVAILABLE", "UNKNOWN"}


# ══════════════════════════════════════════════════════════════════════════
# Authority and purity
# ══════════════════════════════════════════════════════════════════════════

def test_contract_has_no_network_dependency():
    import pathlib

    import saathi.platform.market_data.contract as m

    src = pathlib.Path(m.__file__).read_text(encoding="utf-8")
    for forbidden in ("requests", "httpx", "urllib", "socket", "aiohttp"):
        assert forbidden not in src


def test_contract_exposes_no_execution_verb():
    import saathi.platform.market_data.contract as m

    forbidden = {"submit", "execute", "approve", "authorize", "place_order", "trade", "buy", "sell"}
    assert not (set(dir(m)) & forbidden)


def test_contract_cannot_reach_the_ledger_or_the_gateway():
    import ast
    import pathlib

    import saathi.platform.market_data.contract as m

    tree = ast.parse(pathlib.Path(m.__file__).read_text(encoding="utf-8"))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            names.append(node.module or "")
    assert not any("fund_ledger" in n or "execution" in n for n in names), names


# ══════════════════════════════════════════════════════════════════════════
# Regressions from fresh-context review: Decimal("0") default conflated
# "field absent" with "legitimately zero"
# ══════════════════════════════════════════════════════════════════════════

def _quote_kwargs(**over):
    kw = dict(
        instrument_id="NEPSE:NABIL", venue="NEPSE", asset_class=AssetClass.EQUITY,
        currency="NPR", point_in_time=_pit(_utc(2026, 1, 1), _utc(2026, 1, 1)),
        provider=_provider(),
    )
    kw.update(over)
    return kw


def test_a_one_sided_quote_never_reports_a_negative_spread():
    """R1: bid=100 with ask left at its default 0 passed construction, and
    spread then returned -100 — a negative spread nothing rejected."""
    q = CanonicalQuote(**_quote_kwargs(bid=Decimal("100"), last=Decimal("100")))
    assert q.is_two_sided is False
    with pytest.raises(ValueError):
        _ = q.spread


def test_a_one_sided_quote_never_reports_a_meaningless_mid():
    """R1: mid was (0 + 100) / 2 = 50, computed from one real side and one absent."""
    q = CanonicalQuote(**_quote_kwargs(ask=Decimal("100"), last=Decimal("100")))
    assert q.is_two_sided is False
    with pytest.raises(ValueError):
        _ = q.mid


def test_a_two_sided_quote_still_reports_spread_and_mid():
    q = CanonicalQuote(**_quote_kwargs(bid=Decimal("534"), ask=Decimal("536"), last=Decimal("535")))
    assert q.is_two_sided is True
    assert q.spread == Decimal("2")
    assert q.mid == Decimal("535")


def test_a_fully_empty_quote_is_not_two_sided():
    q = CanonicalQuote(**_quote_kwargs())
    assert q.is_two_sided is False


def _bar_kwargs(**over):
    kw = dict(
        instrument_id="NEPSE:NABIL", venue="NEPSE", asset_class=AssetClass.EQUITY,
        currency="NPR", point_in_time=_pit(_utc(2026, 1, 1), _utc(2026, 1, 2)),
        provider=_provider(),
    )
    kw.update(over)
    return kw


def test_a_partially_populated_bar_is_rejected():
    """R2: open=low=close=0 with high=100 satisfied 0 <= 0 <= 100 and passed.
    A bar that traded up to 100 cannot have a low of zero."""
    with pytest.raises(ValueError):
        CanonicalBar(**_bar_kwargs(high=Decimal("100")))


def test_a_bar_with_only_a_close_is_rejected():
    with pytest.raises(ValueError):
        CanonicalBar(**_bar_kwargs(close=Decimal("98")))


def test_an_all_zero_bar_is_permitted_as_a_no_trade_session():
    """A genuinely empty session is representable; a half-empty one is not."""
    bar = CanonicalBar(**_bar_kwargs())
    assert bar.volume == Decimal("0")


def test_a_fully_populated_bar_still_validates_normally():
    bar = CanonicalBar(**_bar_kwargs(
        open=Decimal("100"), high=Decimal("110"), low=Decimal("95"),
        close=Decimal("98"), volume=Decimal("1000"),
    ))
    assert bar.close == Decimal("98")
