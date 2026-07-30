"""M258 — Deterministic schema normalisation for OHLCV and related families."""
from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from saathi.platform.tg.market_data.models import (
    CANONICAL_OHLCV_FIELDS,
    COLUMN_ALIASES,
    INGESTION_VERSION,
    RowStatus,
)


def map_columns(headers: list[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for h in headers:
        key = h.strip()
        if key in COLUMN_ALIASES:
            mapping[key] = COLUMN_ALIASES[key]
        elif key.lower() in COLUMN_ALIASES:
            mapping[key] = COLUMN_ALIASES[key.lower()]
        else:
            low = key.lower().replace(" ", "_")
            if low in CANONICAL_OHLCV_FIELDS or low in (
                "open", "high", "low", "close", "volume", "symbol", "timestamp",
                "adjusted_close", "exchange", "currency", "interval", "vwap", "trade_count",
            ):
                mapping[key] = low
            else:
                mapping[key] = low
    return mapping


def parse_timestamp(value: Any, tz_name: str = "UTC") -> tuple[str | None, str | None]:
    """Return (iso_timestamp, error_reason)."""
    if value is None or value == "":
        return None, "missing_timestamp"
    s = str(value).strip()
    # CSV injection: reject formula-like timestamps
    if s[:1] in ("=", "+", "@") or (s[:1] == "-" and not re.match(r"^-?\d", s)):
        return None, "csv_injection_or_malformed_timestamp"
    formats = (
        "%Y-%m-%d",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d %H:%M:%S",
        "%Y/%m/%d",
        "%d-%m-%Y",
        "%m/%d/%Y",
    )
    for fmt in formats:
        try:
            dt = datetime.strptime(s.replace("Z", ""), fmt.replace("Z", ""))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), None
        except ValueError:
            continue
    # epoch seconds / millis
    try:
        num = float(s)
        if num > 1e12:
            num = num / 1000.0
        if num < 0:
            return None, "negative_epoch"
        dt = datetime.fromtimestamp(num, tz=timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ"), None
    except (ValueError, OSError, OverflowError):
        return None, "unparseable_timestamp"


def parse_decimal(value: Any, field: str) -> tuple[float | None, str | None]:
    if value is None or value == "":
        return None, f"missing_{field}"
    s = str(value).strip().replace(",", "")
    if s[:1] in ("=", "+", "@"):
        return None, f"csv_injection_{field}"
    try:
        d = Decimal(s)
    except (InvalidOperation, ValueError):
        return None, f"invalid_decimal_{field}"
    f = float(d)
    if not math.isfinite(f):
        return None, f"non_finite_{field}"
    return f, None


def normalize_ohlcv_row(
    raw: dict[str, Any],
    *,
    dataset_id: str,
    source_row_ref: str,
    defaults: dict[str, Any] | None = None,
) -> tuple[dict[str, Any] | None, str, list[str]]:
    """
    Normalize one row. Returns (row_or_none, status, reasons).
    Does not silently repair invalid OHLC relationships.
    """
    defaults = defaults or {}
    reasons: list[str] = []
    mapped: dict[str, Any] = {}
    for k, v in raw.items():
        mk = COLUMN_ALIASES.get(k) or COLUMN_ALIASES.get(k.strip()) or k.strip().lower().replace(" ", "_")
        mapped[mk] = v

    symbol = str(mapped.get("symbol") or defaults.get("symbol") or "").strip().upper()
    if not symbol:
        return None, RowStatus.REJECTED.value, ["missing_symbol"]

    ts, ts_err = parse_timestamp(mapped.get("timestamp") or mapped.get("date"), defaults.get("timezone", "UTC"))
    if ts_err:
        return None, RowStatus.REJECTED.value, [ts_err]

    fields = {}
    for f in ("open", "high", "low", "close"):
        val, err = parse_decimal(mapped.get(f), f)
        if err:
            return None, RowStatus.REJECTED.value, [err]
        fields[f] = val

    adj, adj_err = parse_decimal(mapped.get("adjusted_close"), "adjusted_close") if mapped.get("adjusted_close") not in (None, "") else (fields["close"], None)
    if adj_err:
        reasons.append(adj_err)
        adj = None

    vol, vol_err = parse_decimal(mapped.get("volume"), "volume") if mapped.get("volume") not in (None, "") else (0.0, None)
    if vol_err:
        return None, RowStatus.REJECTED.value, [vol_err]

    # Explicit integrity: do not repair
    o, h, l, c = fields["open"], fields["high"], fields["low"], fields["close"]
    if any(x is not None and x < 0 for x in (o, h, l, c, adj if adj is not None else 0)):
        return None, RowStatus.REJECTED.value, ["negative_price"]
    if h < l:
        return None, RowStatus.REJECTED.value, ["high_below_low"]
    if o > h or o < l:
        return None, RowStatus.QUARANTINED.value, ["open_outside_high_low"]
    if c > h or c < l:
        return None, RowStatus.QUARANTINED.value, ["close_outside_high_low"]
    if vol is not None and vol < 0:
        return None, RowStatus.REJECTED.value, ["negative_volume"]

    instrument_id = str(mapped.get("instrument_id") or f"{defaults.get('exchange', 'XNAS')}:{symbol}")
    row = {
        "instrument_id": instrument_id,
        "symbol": symbol,
        "exchange": str(mapped.get("exchange") or defaults.get("exchange") or ""),
        "asset_class": str(mapped.get("asset_class") or defaults.get("asset_class") or "equity"),
        "timestamp": ts,
        "timezone": str(defaults.get("timezone") or "UTC"),
        "interval": str(mapped.get("interval") or defaults.get("frequency") or "1d"),
        "open": o,
        "high": h,
        "low": l,
        "close": c,
        "adjusted_close": adj if adj is not None else c,
        "volume": vol,
        "trade_count": None,
        "vwap": None,
        "currency": str(mapped.get("currency") or defaults.get("currency") or "USD"),
        "source_dataset_id": dataset_id,
        "source_row_ref": source_row_ref,
        "ingestion_version": INGESTION_VERSION,
    }
    if mapped.get("trade_count") not in (None, ""):
        tc, _ = parse_decimal(mapped.get("trade_count"), "trade_count")
        row["trade_count"] = tc
    if mapped.get("vwap") not in (None, ""):
        vw, _ = parse_decimal(mapped.get("vwap"), "vwap")
        row["vwap"] = vw

    status = RowStatus.NORMALIZED.value if not reasons else RowStatus.ACCEPTED.value
    return row, status, reasons
