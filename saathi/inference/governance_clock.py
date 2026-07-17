"""M24 — Canonical clock and budget-day timezone for provider governance.

All durable timestamps are stored as UTC epoch seconds (float, second precision).
Daily budget boundaries use an explicit configured timezone — never host-local
implicit timezone. Tests inject a deterministic clock.
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Callable, Optional
from zoneinfo import ZoneInfo

Clock = Callable[[], float]

# Canonical budget-day timezone. Override via SAATHI_BUDGET_DAY_TZ (IANA name).
# Default UTC — do not assume Nepal/Asia/Kathmandu unless operator configures it.
DEFAULT_BUDGET_DAY_TZ = "UTC"
_FUTURE_SKEW_TOLERANCE_SECONDS = 300.0  # 5 minutes


def budget_day_timezone_name() -> str:
    raw = (os.getenv("SAATHI_BUDGET_DAY_TZ") or DEFAULT_BUDGET_DAY_TZ).strip()
    return raw or DEFAULT_BUDGET_DAY_TZ


def budget_day_zone() -> ZoneInfo:
    name = budget_day_timezone_name()
    try:
        return ZoneInfo(name)
    except Exception as e:
        raise ValueError(f"invalid budget day timezone: {name}") from e


def utc_now() -> float:
    """Canonical wall clock — UTC epoch seconds."""
    return time.time()


def day_key(ts: Optional[float] = None, *, tz_name: Optional[str] = None) -> str:
    """YYYY-MM-DD in the configured budget-day timezone."""
    t = float(ts if ts is not None else utc_now())
    name = tz_name or budget_day_timezone_name()
    try:
        z = ZoneInfo(name)
    except Exception:
        z = timezone.utc
        name = "UTC"
    dt = datetime.fromtimestamp(t, tz=timezone.utc).astimezone(z)
    return dt.strftime("%Y-%m-%d")


def validate_timestamp(
    ts: float,
    *,
    clock: Optional[Clock] = None,
    future_tolerance: float = _FUTURE_SKEW_TOLERANCE_SECONDS,
) -> tuple[bool, str]:
    """Conservative clock-skew check. Future beyond tolerance fails safely."""
    now = float((clock or utc_now)())
    t = float(ts)
    if t < 0:
        return False, "timestamp_negative"
    if t > now + float(future_tolerance):
        return False, "timestamp_future_skew"
    return True, "ok"


class DeterministicClock:
    """Injectable monotonic-capable test clock (epoch seconds)."""

    def __init__(self, start: float = 1_700_000_000.0) -> None:
        self._t = float(start)

    def __call__(self) -> float:
        return self._t

    def advance(self, seconds: float) -> float:
        self._t += float(seconds)
        return self._t

    def set(self, ts: float) -> float:
        self._t = float(ts)
        return self._t
