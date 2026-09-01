"""M259 — Exchange calendar integrity (equity sessions vs 24/7 crypto)."""
from __future__ import annotations

import json
import time
from datetime import date, datetime
from typing import Any

from saathi.platform.nepse.calendar import (
    NEPAL_TZ,
    NEPAL_TZ_NAME,
    NEPSE_CALENDAR_V2_CANONICAL,
    NEPSE_CLOSE_LOCAL,
    NEPSE_OPEN_LOCAL,
    CalendarCoverageStatus,
    NepseCalendar,
    SessionClassification,
)
from saathi.platform.tg.market_data.models import AUTHORITY_VALUES
from saathi.platform.tg.market_data.storage import MarketDataStore, _uid

# Minimal built-in holiday samples (not exhaustive — research limitation)
US_EQUITY_HOLIDAYS_SAMPLE = {
    "2024-01-01", "2024-01-15", "2024-02-19", "2024-03-29", "2024-05-27",
    "2024-06-19", "2024-07-04", "2024-09-02", "2024-11-28", "2024-12-25",
    "2025-01-01", "2025-01-20", "2025-02-17", "2025-04-18", "2025-05-26",
    "2025-06-19", "2025-07-04", "2025-09-01", "2025-11-27", "2025-12-25",
}

DEFAULT_SESSIONS = {
    "XNAS": {"open": "09:30", "close": "16:00", "timezone": "America/New_York", "asset_class": "equity"},
    "XNYS": {"open": "09:30", "close": "16:00", "timezone": "America/New_York", "asset_class": "equity"},
    "CRYPTO": {"open": "00:00", "close": "23:59", "timezone": "UTC", "asset_class": "crypto", "is_247": True},
}


class CalendarEngine:
    def __init__(self, store: MarketDataStore):
        self.store = store
        self._bootstrap()

    def _bootstrap(self) -> None:
        for exch, cfg in DEFAULT_SESSIONS.items():
            existing = self.store.query_one("SELECT id FROM md_calendars WHERE exchange=?", (exch,))
            if existing:
                continue
            self.store.execute(
                """INSERT INTO md_calendars(
                    id, exchange, market, asset_class, sessions_json, holidays_json,
                    early_closes_json, timezone, is_247, created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (
                    _uid("cal"), exch,
                    "US" if exch in ("XNAS", "XNYS") else "GLOBAL",
                    cfg["asset_class"],
                    json.dumps({"open": cfg["open"], "close": cfg["close"]}),
                    json.dumps(sorted(US_EQUITY_HOLIDAYS_SAMPLE) if cfg["asset_class"] == "equity" else []),
                    json.dumps([]),
                    cfg["timezone"],
                    1 if cfg.get("is_247") else 0,
                    time.time(),
                ),
            )

    def get(self, exchange: str) -> dict[str, Any]:
        if exchange.upper() == "NEPSE":
            calendar = NepseCalendar()
            return {
                "ok": True,
                "exchange": "NEPSE",
                "market": "NEPSE",
                "asset_class": "equity",
                "sessions": {
                    "open": NEPSE_OPEN_LOCAL.strftime("%H:%M"),
                    "close": NEPSE_CLOSE_LOCAL.strftime("%H:%M"),
                },
                "holidays": [],
                "early_closes": [],
                "timezone": NEPAL_TZ_NAME,
                "is_247": False,
                "calendar_version": NEPSE_CALENDAR_V2_CANONICAL,
                "calendar_source_version": calendar.calendar_source_version,
                "calendar_coverage_status": CalendarCoverageStatus.HOLIDAY_COVERAGE_UNKNOWN.value,
                "limitations": ["NEPSE holiday coverage is unavailable; weekly candidates remain unknown"],
                **AUTHORITY_VALUES,
            }
        row = self.store.query_one("SELECT * FROM md_calendars WHERE exchange=?", (exchange,))
        if not row:
            return {"ok": False, "code": "CALENDAR_NOT_FOUND", "exchange": exchange, **AUTHORITY_VALUES}
        return {
            "ok": True,
            "exchange": row["exchange"],
            "market": row["market"],
            "asset_class": row["asset_class"],
            "sessions": json.loads(row["sessions_json"]),
            "holidays": json.loads(row["holidays_json"]),
            "early_closes": json.loads(row["early_closes_json"]),
            "timezone": row["timezone"],
            "is_247": bool(row["is_247"]),
            "limitations": ["Holiday calendars are sample/incomplete — not exchange-official full history"],
            **AUTHORITY_VALUES,
        }

    def check_bars(self, dataset_id: str, dataset_version: str) -> dict[str, Any]:
        ds = self.store.get_dataset(dataset_id, dataset_version)
        bars = self.store.query(
            "SELECT symbol, timestamp, asset_class FROM md_bars WHERE dataset_id=? AND dataset_version=?",
            (dataset_id, dataset_version),
        )
        exchange = str((ds or {}).get("exchange") or "").upper()
        if exchange in ("", "UNKNOWN"):
            return {
                "ok": False,
                "code": "UNKNOWN_VENUE",
                "exchange": "UNKNOWN",
                "asset_class": (ds or {}).get("asset_class") or "UNKNOWN",
                "issues": [{"code": "unknown_dataset_venue"}],
                **AUTHORITY_VALUES,
            }
        asset_class = (ds or {}).get("asset_class") or "equity"
        cal = self.get(exchange if asset_class != "crypto" else "CRYPTO")
        issues = []
        if asset_class == "crypto" or cal.get("is_247"):
            # Do not apply equity weekend rules to crypto
            return {
                "ok": True,
                "exchange": "CRYPTO",
                "asset_class": "crypto",
                "is_247": True,
                "issues": [],
                "note": "Crypto 24/7 — equity session rules not applied",
                **AUTHORITY_VALUES,
            }
        if exchange.upper() == "NEPSE":
            canonical = NepseCalendar()
            for bar in bars:
                raw_timestamp = bar["timestamp"] or ""
                try:
                    parsed = datetime.fromisoformat(raw_timestamp.replace("Z", "+00:00"))
                    local_day = (
                        parsed.astimezone(NEPAL_TZ).date()
                        if parsed.tzinfo is not None
                        else date.fromisoformat(raw_timestamp[:10])
                    )
                except (TypeError, ValueError):
                    issues.append({"code": "invalid_date", "ts": raw_timestamp})
                    continue
                classification = canonical.classify_session(local_day)
                if classification is SessionClassification.CONFIRMED_CLOSED:
                    issues.append(
                        {
                            "code": "confirmed_closed_session_bar",
                            "symbol": bar["symbol"],
                            "ts": raw_timestamp,
                        }
                    )
                elif classification in (
                    SessionClassification.POTENTIAL_OPEN_HOLIDAY_UNKNOWN,
                    SessionClassification.UNKNOWN,
                ):
                    issues.append(
                        {
                            "code": "calendar_coverage_unknown",
                            "symbol": bar["symbol"],
                            "ts": raw_timestamp,
                        }
                    )
            return {
                "ok": True,
                "exchange": "NEPSE",
                "asset_class": "equity",
                "is_247": False,
                "issue_count": len(issues),
                "issues": issues[:100],
                "sessions": cal.get("sessions"),
                "timezone": NEPAL_TZ_NAME,
                "calendar_version": NEPSE_CALENDAR_V2_CANONICAL,
                "calendar_source_version": canonical.calendar_source_version,
                "calendar_coverage_status": CalendarCoverageStatus.HOLIDAY_COVERAGE_UNKNOWN.value,
                **AUTHORITY_VALUES,
            }
        holidays = set(cal.get("holidays") or [])
        for b in bars:
            day = (b["timestamp"] or "")[:10]
            try:
                d = datetime.strptime(day, "%Y-%m-%d")
            except ValueError:
                issues.append({"code": "invalid_date", "ts": b["timestamp"]})
                continue
            if d.weekday() >= 5:
                issues.append({"code": "unexpected_weekend_bar", "symbol": b["symbol"], "ts": b["timestamp"]})
            if day in holidays:
                issues.append({"code": "unexpected_holiday_bar", "symbol": b["symbol"], "ts": b["timestamp"]})
        return {
            "ok": True,
            "exchange": exchange,
            "asset_class": asset_class,
            "is_247": False,
            "issue_count": len(issues),
            "issues": issues[:100],
            "sessions": cal.get("sessions"),
            "timezone": cal.get("timezone"),
            **AUTHORITY_VALUES,
        }
