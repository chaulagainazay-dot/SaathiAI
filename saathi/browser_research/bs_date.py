"""Phase 10-12 — Nepali Bikram Sambat (BS) date parsing + deterministic BS→AD.

No LLM, no runtime dependency. The month-length table (BS 2075..2092) and the
anchor (BS 2075-01-01 = AD 2018-04-14) were extracted once from the vetted
``nepali-datetime`` library and embedded here for offline determinism. The raw
source date is ALWAYS preserved; conversion never overwrites it. When the
calendar cannot be proven, ``calendar = UNKNOWN`` (never guessed).
"""
from __future__ import annotations

import datetime as _dt
import re
from dataclasses import dataclass
from enum import Enum

ANCHOR_BS = (2075, 1, 1)
ANCHOR_AD = _dt.date(2018, 4, 14)

# Days per BS month (Baishakh..Chaitra), authoritative for 2075..2092.
BS_MONTH_DAYS: dict[int, list[int]] = {
    2075: [31, 31, 32, 31, 31, 31, 30, 29, 30, 29, 30, 30],
    2076: [31, 32, 31, 32, 31, 30, 30, 30, 29, 29, 30, 30],
    2077: [31, 32, 31, 32, 31, 30, 30, 30, 29, 30, 29, 31],
    2078: [31, 31, 31, 32, 31, 31, 30, 29, 30, 29, 30, 30],
    2079: [31, 31, 32, 31, 31, 31, 30, 29, 30, 29, 30, 30],
    2080: [31, 32, 31, 32, 31, 30, 30, 30, 29, 29, 30, 30],
    2081: [31, 32, 31, 32, 31, 30, 30, 30, 29, 30, 29, 31],
    2082: [31, 31, 32, 31, 31, 31, 30, 29, 30, 29, 30, 30],
    2083: [31, 31, 32, 31, 31, 31, 30, 29, 30, 29, 30, 30],
    2084: [31, 31, 32, 31, 31, 30, 30, 30, 29, 30, 30, 30],
    2085: [31, 32, 31, 32, 30, 31, 30, 30, 29, 30, 30, 30],
    2086: [30, 32, 31, 32, 31, 30, 30, 30, 29, 30, 30, 30],
    2087: [31, 31, 32, 31, 31, 31, 30, 29, 30, 30, 30, 30],
    2088: [30, 31, 32, 32, 30, 31, 30, 30, 29, 30, 30, 30],
    2089: [30, 32, 31, 32, 31, 30, 30, 30, 29, 30, 30, 30],
    2090: [30, 32, 31, 32, 31, 30, 30, 30, 29, 30, 30, 30],
    2091: [31, 31, 32, 31, 31, 31, 30, 30, 29, 30, 30, 30],
    2092: [30, 31, 32, 32, 31, 30, 30, 30, 29, 30, 30, 30],
}
BS_MIN_YEAR = min(BS_MONTH_DAYS)
BS_MAX_YEAR = max(BS_MONTH_DAYS)

# Nepali (Devanagari) digit transliteration.
_NEP_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")

_DATE_RE = re.compile(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})")
_BS_HINT_RE = re.compile(r"(?i)(b\.?s\.?|bikram|बि\.?सं|साल|२०[६-९]\d)")
_AD_HINT_RE = re.compile(r"(?i)(a\.?d\.?|gregorian|ई\.?सं)")


class Calendar(str, Enum):
    BS = "BS"
    AD = "AD"
    AMBIGUOUS = "AMBIGUOUS"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class DateResult:
    raw: str
    calendar: Calendar
    ad_date: _dt.date | None = None

    @property
    def ad_ts(self) -> float | None:
        if self.ad_date is None:
            return None
        return _dt.datetime(self.ad_date.year, self.ad_date.month, self.ad_date.day,
                            tzinfo=_dt.timezone.utc).timestamp()


def is_valid_bs(y: int, m: int, d: int) -> bool:
    if y not in BS_MONTH_DAYS or not (1 <= m <= 12):
        return False
    return 1 <= d <= BS_MONTH_DAYS[y][m - 1]


def bs_to_ad(y: int, m: int, d: int) -> _dt.date:
    """Deterministic BS→AD. Raises ValueError for out-of-range/invalid input."""
    if not is_valid_bs(y, m, d):
        raise ValueError(f"invalid or unsupported BS date {y}-{m}-{d}")
    days = 0
    for yy in range(ANCHOR_BS[0], y):
        days += sum(BS_MONTH_DAYS[yy])
    days += sum(BS_MONTH_DAYS[y][: m - 1])
    days += (d - 1)
    return ANCHOR_AD + _dt.timedelta(days=days)


def _valid_ad(y: int, m: int, d: int) -> _dt.date | None:
    try:
        return _dt.date(y, m, d)
    except ValueError:
        return None


def parse_date(text: str, *, calendar_hint: str | None = None) -> DateResult:
    """Parse a date string, preserving the raw value and choosing a calendar.

    calendar_hint ('BS'/'AD') forces interpretation (used by source-aware
    extractors that know their site publishes BS). Without a hint the calendar
    is inferred; genuine overlap → AMBIGUOUS; nothing parseable → UNKNOWN.
    """
    if not text:
        return DateResult(raw=text or "", calendar=Calendar.UNKNOWN)
    norm = text.translate(_NEP_DIGITS)
    m = _DATE_RE.search(norm)
    if not m:
        return DateResult(raw=text, calendar=Calendar.UNKNOWN)
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))

    hint = (calendar_hint or "").upper() or None
    if hint is None:
        if _BS_HINT_RE.search(text):
            hint = "BS"
        elif _AD_HINT_RE.search(text):
            hint = "AD"

    bs_ok = is_valid_bs(y, mo, d)
    ad_ok = _valid_ad(y, mo, d)

    if hint == "BS":
        return (DateResult(text, Calendar.BS, bs_to_ad(y, mo, d)) if bs_ok
                else DateResult(text, Calendar.UNKNOWN))
    if hint == "AD":
        return (DateResult(text, Calendar.AD, ad_ok) if ad_ok
                else DateResult(text, Calendar.UNKNOWN))

    # No hint — infer.
    if y > BS_MAX_YEAR:
        # BS 2093+ is a plausible near-future notice; AD 2093+ is not.
        return DateResult(text, Calendar.UNKNOWN)
    if bs_ok and ad_ok:
        # e.g. 2081-05-27 is valid as both BS(→2024) and AD(2081) — cannot prove.
        return DateResult(text, Calendar.AMBIGUOUS)
    if bs_ok:
        return DateResult(text, Calendar.BS, bs_to_ad(y, mo, d))
    if ad_ok and 1970 <= y <= 2035:
        return DateResult(text, Calendar.AD, ad_ok)
    return DateResult(text, Calendar.UNKNOWN)
