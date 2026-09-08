"""FINANCIAL-NUMERIC-1 — financial numeric parsing fails closed.

The defect this closes: a parser that swallowed every failure and returned zero,
so "abc", True, object() and a ShadowOrder all became Decimal("0") — a
valid-looking amount manufactured from garbage, on paths reaching cash
reservation, Guardian risk inputs and safety metrics.

The invariant: A PARSER DOES NOT CREATE ECONOMIC MEANING. It answers "is this a
valid numeric representation?". Whether ABSENCE means zero is the caller's policy
and must be written at the caller.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from saathi.platform.fund_ledger.money import D as MONEY_D, MoneyError
from saathi.platform.trading_models import D as TRADING_D, InvalidFinancialValue

PARSERS = (
    pytest.param(TRADING_D, InvalidFinancialValue, id="trading_models.D"),
    pytest.param(MONEY_D, MoneyError, id="fund_ledger.money.D"),
)

# Everything a financial parser must refuse rather than turn into a number.
HOSTILE = [
    "abc", "not-a-number", "   ", "1.2.3", "--1", "1,000",
    "NaN", "nan", "sNaN", "Infinity", "-Infinity", "inf",
    Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity"),
    float("nan"), float("inf"), float("-inf"),
    object(), [], {}, (), set(), b"1", complex(1, 2),
]


@pytest.mark.parametrize("parse,err", PARSERS)
@pytest.mark.parametrize("value", HOSTILE, ids=lambda v: repr(v)[:24])
def test_invalid_input_is_refused_never_zeroed(parse, err, value):
    with pytest.raises(err):
        parse(value)


@pytest.mark.parametrize("parse,err", PARSERS)
def test_bool_is_not_a_financial_value(parse, err):
    """isinstance(True, int) is True in Python.

    Without an explicit guard a parser turns True into 1 and False into 0 — a
    quantity of one and an amount of zero, conjured from a flag.
    """
    for b in (True, False):
        with pytest.raises(err):
            parse(b)


@pytest.mark.parametrize("parse,err", PARSERS)
def test_nan_can_never_reach_financial_state(parse, err):
    """NaN is refused at the parser because it fails QUIETLY where it matters.

    Python's Decimal raises on an ordering comparison, which sounds safe — but by
    then the NaN has usually travelled a long way, because arithmetic propagates
    it silently, ``== 0`` misses it, and it is truthy. The exception surfaces far
    from the value that caused it. Infinity does not even raise: it compares, and
    a limit check simply returns the wrong answer.
    """
    for nan_ish in ("NaN", Decimal("NaN"), float("nan")):
        with pytest.raises(err):
            parse(nan_ish)
    # The exact semantics this guard exists for, pinned so the rationale in the
    # source stays true.
    nan = Decimal("NaN")
    assert (nan + Decimal("1")).is_nan(), "arithmetic propagates it silently"
    assert (nan == Decimal("0")) is False, "a zero check misses it"
    assert bool(nan) is True, "and it is truthy, so `if amount:` passes"
    with pytest.raises(Exception):
        _ = nan > Decimal("1")     # only here does it finally raise
    assert Decimal("Infinity") > Decimal("1"), "infinity does not even raise"


@pytest.mark.parametrize("parse,err", PARSERS)
def test_infinity_is_refused(parse, err):
    for inf in ("Infinity", "-Infinity", Decimal("Infinity"), float("inf"), float("-inf")):
        with pytest.raises(err):
            parse(inf)


@pytest.mark.parametrize("parse,err", PARSERS)
def test_pathological_input_cannot_be_used_to_exhaust_the_parser(parse, err):
    """Decimal will happily consume a megabyte of digits. A financial parser
    reachable from provider and model output must not."""
    for hostile in ("1e999999", "9" * 400, "1" * 5000, "-1e999999"):
        with pytest.raises(err):
            parse(hostile)


# ── what must still work ────────────────────────────────────────────────────

@pytest.mark.parametrize("parse,err", PARSERS)
def test_legitimate_values_are_preserved(parse, err):
    assert parse(Decimal("0")) == Decimal("0")
    assert parse(Decimal("1.25")) == Decimal("1.25")
    assert parse(Decimal("-42.50")) == Decimal("-42.50")
    assert parse(0) == Decimal("0")
    assert parse(1) == Decimal("1")
    assert parse("0") == Decimal("0")
    assert parse("1.25") == Decimal("1.25")
    assert parse("-1.25") == Decimal("-1.25")


@pytest.mark.parametrize("parse,err", PARSERS)
def test_a_legitimate_zero_is_not_the_defect(parse, err):
    """This milestone forbids INVALID becoming zero. Zero itself is a real
    amount and must survive untouched."""
    assert parse("0") == Decimal("0")
    assert parse(Decimal("0.00")) == Decimal("0.00")


@pytest.mark.parametrize("parse,err", PARSERS)
def test_absence_remains_the_callers_declared_default(parse, err):
    """None/"" yield the caller's default — a declared policy, not a parse result.

    The parser does not decide that a missing fee is zero; the caller passes the
    default it means, which keeps the policy visible at the call site.
    """
    assert parse(None) == Decimal("0")
    assert parse("") == Decimal("0")
    assert parse(None, default="5") == Decimal("5")


@pytest.mark.parametrize("parse,err", PARSERS)
def test_negative_representation_is_valid_even_where_it_is_economically_wrong(parse, err):
    """Representation and economics are separate concerns.

    -1 is a perfectly valid number and a legitimate P&L; whether a BUY may have a
    negative quantity is a domain rule, enforced by the domain, not the parser.
    """
    assert parse("-1") == Decimal("-1")
    assert parse(Decimal("-0.01")) == Decimal("-0.01")


def test_both_parsers_agree_on_every_case():
    """Two implementations exist; they must not drift apart.

    fund_ledger.money.D also rejects floats (money must never come from binary
    float); trading_models.D accepts them via str, which is the one deliberate
    difference and is asserted here so it stays deliberate.
    """
    for value in HOSTILE + [True, False]:
        t = pytest.raises(InvalidFinancialValue)
        m = pytest.raises(MoneyError)
        with t:
            TRADING_D(value)
        with m:
            MONEY_D(value)
    for value in (Decimal("1.25"), 0, 1, "0", "1.25", "-1", None, ""):
        assert TRADING_D(value) == MONEY_D(value)
    # The deliberate difference.
    with pytest.raises(MoneyError):
        MONEY_D(1.5)
    assert TRADING_D(1.5) == Decimal("1.5")


# ── the money path itself ───────────────────────────────────────────────────

def test_reserve_for_buy_fails_closed_on_malformed_input():
    """No malformed input may produce a successful reservation."""
    from saathi.platform.paper_trading.broker import FeeModel, PaperBroker, SlippageModel
    from saathi.platform.paper_trading.models import OrderType

    broker = PaperBroker(fee_model=FeeModel(), slippage_model=SlippageModel())
    for bad_qty in ("abc", True, object(), float("nan"), "Infinity"):
        with pytest.raises(Exception):
            broker.reserve_for_buy(quantity=bad_qty, ref_price=Decimal("60000"),
                                   limit_price=None, order_type=OrderType.MARKET)
    for bad_px in ("abc", True, object(), float("nan")):
        with pytest.raises(Exception):
            broker.reserve_for_buy(quantity=Decimal("1"), ref_price=bad_px,
                                   limit_price=None, order_type=OrderType.MARKET)

    # A real reservation still computes. The default fee and slippage models are
    # zero, so with them the reservation is exactly the notional.
    ok = broker.reserve_for_buy(quantity=Decimal("1"), ref_price=Decimal("60000"),
                                limit_price=None, order_type=OrderType.MARKET)
    assert ok == Decimal("60000.00")
    costed = PaperBroker(
        fee_model=FeeModel(pct=Decimal("0.001")),
        slippage_model=SlippageModel(bps=Decimal("10")),
    ).reserve_for_buy(quantity=Decimal("1"), ref_price=Decimal("60000"),
                      limit_price=None, order_type=OrderType.MARKET)
    assert costed > Decimal("60000"), "notional + fee + slippage reserve"


def test_guardian_risk_inputs_fail_closed():
    """coerce_decimal wrapped D() in a bare except and returned zero.

    A stop distance of zero is not a small risk — it is a risk check that cannot
    fail. Malformed Guardian inputs must refuse, not evaluate against fabricated
    numbers.
    """
    from saathi.platform.tg.domain import coerce_decimal

    for bad in ("abc", True, object(), float("nan"), "Infinity"):
        with pytest.raises(Exception):
            coerce_decimal(bad)
    assert coerce_decimal(None) == Decimal("0")
    assert coerce_decimal("1.25") == Decimal("1.25")


def test_qualification_evidence_fails_closed():
    from saathi.platform.tg.historical.qualification import _dec

    for bad in ("abc", True, object(), float("nan")):
        with pytest.raises(Exception):
            _dec(bad)
    assert _dec(None) == Decimal("0")
    assert _dec("0.75") == Decimal("0.75")


def test_a_provider_string_cannot_become_a_price():
    """The security case: malformed EXTERNAL data must not become a number.

    A provider or model value that fails to parse used to arrive downstream as a
    valid-looking zero price, indistinguishable from a real zero.
    """
    from saathi.platform.trading_models import D

    for provider_junk in ("N/A", "-", "null", "None", "--", "1 234", "$60,000"):
        with pytest.raises(InvalidFinancialValue):
            D(provider_junk)


# ── strict representation + required-value boundary ─────────────────────────

@pytest.mark.parametrize("parse,err", PARSERS)
def test_only_a_plain_numeric_representation_is_accepted(parse, err):
    """Decimal accepts more syntaxes than a financial feed ever emits.

    PEP-515 underscores were the live example: ``"1_000"`` parsed to 1000 and
    produced a 60,000,000 cash reservation. An unexpected accepted SYNTAX is an
    unexpected accepted VALUE when the input comes from a provider or a model.
    """
    for exotic in ("1_000", "0x10", "0b11", "1 234", " 1 ", "\t1", "1\n", "+ 1", "1e", "e5"):
        with pytest.raises(err):
            parse(exotic)
    # Ordinary forms still parse.
    for ok in ("1", "0", "-1.25", "+2.5", ".5", "1.", "1e5", "-1E-3"):
        assert isinstance(parse(ok), Decimal)


def test_reserve_for_buy_requires_a_quantity_and_a_price():
    """Absence is refused at the money boundary, not parsed into zero.

    D() maps None to its default of zero — correct for an optional field, wrong
    here: a missing quantity used to yield a 0.00 reservation, i.e. a buy admitted
    against no reserved cash.
    """
    from saathi.platform.paper_trading.broker import FeeModel, PaperBroker, SlippageModel
    from saathi.platform.paper_trading.models import OrderType

    broker = PaperBroker(fee_model=FeeModel(), slippage_model=SlippageModel())
    with pytest.raises(ValueError):
        broker.reserve_for_buy(quantity=None, ref_price=Decimal("60000"),
                               limit_price=None, order_type=OrderType.MARKET)
    with pytest.raises(ValueError):
        broker.reserve_for_buy(quantity=Decimal("1"), ref_price=None,
                               limit_price=None, order_type=OrderType.MARKET)
    # A genuine zero quantity is still a legal, explicit request.
    assert broker.reserve_for_buy(quantity=Decimal("0"), ref_price=Decimal("60000"),
                                  limit_price=None, order_type=OrderType.MARKET) == Decimal("0.00")


def test_no_hostile_provider_value_can_produce_a_reservation():
    """The security case, end to end at the money boundary."""
    from saathi.platform.paper_trading.broker import FeeModel, PaperBroker, SlippageModel
    from saathi.platform.paper_trading.models import OrderType

    broker = PaperBroker(fee_model=FeeModel(), slippage_model=SlippageModel())
    hostile = ["N/A", "null", "None", "undefined", "-", "--", "$60,000", "1 234",
               "NaN", "Infinity", "1e999999", "0x10", "1_000", True, None, object()]
    for value in hostile:
        with pytest.raises(Exception):
            broker.reserve_for_buy(quantity=value, ref_price=Decimal("60000"),
                                   limit_price=None, order_type=OrderType.MARKET)
