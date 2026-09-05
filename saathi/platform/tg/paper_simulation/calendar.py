"""Trading calendar for paper simulation sessions."""
from __future__ import annotations

from typing import Any

from saathi.platform.nepse.calendar import (
    NEPAL_TZ_NAME,
    NEPSE_CALENDAR_V2_CANONICAL,
    NEPSE_CLOSE_LOCAL,
    NEPSE_OPEN_LOCAL,
    NEPSE_TRADING_WEEKDAYS,
    CalendarCoverageStatus,
    NepseCalendar,
)
from saathi.platform.tg.paper_simulation.models import AUTHORITY_VALUES


class TradingCalendar:
    """Simple equity vs crypto session rules (simulated)."""

    EQUITY_HOURS = {"open": "09:30", "close": "16:00", "timezone": "America/New_York"}
    CRYPTO_HOURS = {"open": "00:00", "close": "23:59", "timezone": "UTC", "is_247": True}

    def for_symbol(self, symbol: str) -> dict[str, Any]:
        sym = symbol.upper()
        if sym.endswith("USDT") or sym in ("BTC", "ETH"):
            return {"ok": True, "symbol": sym, "asset_class": "crypto", **self.CRYPTO_HOURS, **AUTHORITY_VALUES}
        if sym.startswith("NEPSE:"):
            calendar = NepseCalendar()
            return {
                "ok": True,
                "symbol": sym,
                "asset_class": "equity",
                "open": NEPSE_OPEN_LOCAL.strftime("%H:%M"),
                "close": NEPSE_CLOSE_LOCAL.strftime("%H:%M"),
                "timezone": NEPAL_TZ_NAME,
                "weekdays": sorted(NEPSE_TRADING_WEEKDAYS),
                "is_247": False,
                "calendar_version": NEPSE_CALENDAR_V2_CANONICAL,
                "calendar_source_version": calendar.calendar_source_version,
                "calendar_coverage_status": CalendarCoverageStatus.HOLIDAY_COVERAGE_UNKNOWN.value,
                **AUTHORITY_VALUES,
            }
        return {"ok": True, "symbol": sym, "asset_class": "equity", **self.EQUITY_HOURS, "is_247": False, **AUTHORITY_VALUES}

    def overview(self) -> dict[str, Any]:
        return {
            "ok": True,
            "equity": self.EQUITY_HOURS,
            "crypto": self.CRYPTO_HOURS,
            "note": "Simulated session calendar — not a live exchange schedule feed",
            **AUTHORITY_VALUES,
        }
