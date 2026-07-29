"""Local CSV and Parquet historical adapter (highest priority).

Local file only. Deterministic parsing. No network. Quarantine on invalid schema.
"""
from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from saathi.platform.tg.historical.adapters.base import AdapterResult, HistoricalAdapter
from saathi.platform.tg.historical.models import AdjustedPriceBar, DatasetSource, fingerprint_payload


# Canonical schema columns (aliases map into these)
CANONICAL = ("timestamp", "instrument", "open", "high", "low", "close", "volume")
ALIASES = {
    "timestamp": {"timestamp", "ts", "time", "date", "datetime", "Date", "Datetime"},
    "instrument": {"instrument", "symbol", "ticker", "Symbol", "Ticker"},
    "open": {"open", "Open", "o"},
    "high": {"high", "High", "h"},
    "low": {"low", "Low", "l"},
    "close": {"close", "Close", "c", "adj_close", "Adj Close"},
    "volume": {"volume", "Volume", "vol", "v"},
}


def _file_fingerprint(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 256)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _parse_ts(val: str, timezone_name: str = "UTC") -> float:
    val = (val or "").strip()
    if not val:
        raise ValueError("empty timestamp")
    # epoch seconds
    try:
        if val.replace(".", "", 1).isdigit():
            return float(val)
    except ValueError:
        pass
    for fmt in (
        "%Y-%m-%d",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d %H:%M:%S",
        "%Y/%m/%d",
        "%m/%d/%Y",
    ):
        try:
            dt = datetime.strptime(val.replace("Z", ""), fmt.replace("Z", ""))
            return dt.replace(tzinfo=timezone.utc).timestamp()
        except ValueError:
            continue
    # fromisoformat fallback
    try:
        dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except ValueError as e:
        raise ValueError(f"unparseable timestamp: {val}") from e


def _dec(val: str) -> Decimal:
    try:
        return Decimal(str(val).strip().replace(",", ""))
    except (InvalidOperation, AttributeError) as e:
        raise ValueError(f"invalid decimal: {val}") from e


def _map_headers(headers: list[str], schema_map: dict[str, str] | None) -> dict[str, str]:
    """Return mapping canonical_field -> actual header name."""
    if schema_map:
        # operator-provided: canonical -> column name
        return {k: schema_map[k] for k in CANONICAL if k in schema_map}
    lower = {h.lower(): h for h in headers}
    mapping: dict[str, str] = {}
    for canon, aliases in ALIASES.items():
        for a in aliases:
            if a in headers:
                mapping[canon] = a
                break
            if a.lower() in lower:
                mapping[canon] = lower[a.lower()]
                break
    return mapping


class LocalFileAdapter(HistoricalAdapter):
    name = "local_file"
    read_only = True
    credentials_required = False
    allows_live_orders = False

    def load(
        self,
        path: str | Path,
        *,
        default_instrument: str = "UNKNOWN",
        timeframe: str = "1d",
        currency: str = "USD",
        timezone_name: str = "UTC",
        schema_map: dict[str, str] | None = None,
        date_range: tuple[float, float] | None = None,
        max_rows: int = 500_000,
    ) -> AdapterResult:
        p = Path(path)
        if not p.is_file():
            return AdapterResult(ok=False, error=f"file_not_found:{p}")
        if p.suffix.lower() not in (".csv", ".parquet", ".pq", ".jsonl"):
            return AdapterResult(ok=False, error=f"unsupported_extension:{p.suffix}")

        try:
            source_fp = _file_fingerprint(p)
        except OSError as e:
            return AdapterResult(ok=False, error=f"read_error:{e}")

        try:
            if p.suffix.lower() in (".parquet", ".pq"):
                bars, warn = self._load_parquet(
                    p,
                    default_instrument=default_instrument,
                    timeframe=timeframe,
                    currency=currency,
                    schema_map=schema_map,
                    date_range=date_range,
                    max_rows=max_rows,
                )
            elif p.suffix.lower() == ".jsonl":
                bars, warn = self._load_jsonl(
                    p,
                    default_instrument=default_instrument,
                    timeframe=timeframe,
                    currency=currency,
                    date_range=date_range,
                    max_rows=max_rows,
                )
            else:
                bars, warn = self._load_csv(
                    p,
                    default_instrument=default_instrument,
                    timeframe=timeframe,
                    currency=currency,
                    timezone_name=timezone_name,
                    schema_map=schema_map,
                    date_range=date_range,
                    max_rows=max_rows,
                )
        except Exception as e:
            return AdapterResult(
                ok=False,
                error=f"parse_failed:{type(e).__name__}:{e}"[:300],
                source_file_fingerprint=source_fp,
            )

        # sort deterministic
        bars.sort(key=lambda b: (b.instrument, b.ts))
        source = DatasetSource(
            adapter="local_csv" if p.suffix.lower() == ".csv" else (
                "local_parquet" if p.suffix.lower() in (".parquet", ".pq") else "local_jsonl"
            ),
            uri=str(p.resolve()),
            read_only=True,
            credentials_required=False,
            network_required=False,
            provenance_notes=["operator-supplied local file", "no network access"],
        )
        return AdapterResult(
            ok=True,
            bars=bars,
            source=source,
            source_file_fingerprint=source_fp,
            warnings=warn,
            metadata={"path": str(p), "row_count": len(bars)},
        )

    def _load_csv(
        self,
        path: Path,
        *,
        default_instrument: str,
        timeframe: str,
        currency: str,
        timezone_name: str,
        schema_map: dict[str, str] | None,
        date_range: tuple[float, float] | None,
        max_rows: int,
    ) -> tuple[list[AdjustedPriceBar], list[str]]:
        warnings: list[str] = []
        bars: list[AdjustedPriceBar] = []
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames:
                raise ValueError("missing_csv_headers")
            mapping = _map_headers(list(reader.fieldnames), schema_map)
            required = {"timestamp", "open", "high", "low", "close"}
            if not required.issubset(mapping.keys()):
                raise ValueError(f"schema_missing_fields:{sorted(required - set(mapping))}")
            for i, row in enumerate(reader):
                if i >= max_rows:
                    warnings.append(f"truncated_at_max_rows:{max_rows}")
                    break
                try:
                    ts = _parse_ts(row[mapping["timestamp"]], timezone_name)
                    if date_range and not (date_range[0] <= ts <= date_range[1]):
                        continue
                    inst = row.get(mapping.get("instrument", ""), "") or default_instrument
                    inst = str(inst).strip().upper()
                    o = _dec(row[mapping["open"]])
                    h = _dec(row[mapping["high"]])
                    l = _dec(row[mapping["low"]])
                    c = _dec(row[mapping["close"]])
                    vol_key = mapping.get("volume")
                    v = _dec(row[vol_key]) if vol_key and row.get(vol_key, "") != "" else Decimal("0")
                    bars.append(AdjustedPriceBar(
                        instrument=inst,
                        ts=ts,
                        open=o, high=h, low=l, close=c, volume=v,
                        adj_open=o, adj_high=h, adj_low=l, adj_close=c,
                        timeframe=timeframe,
                        currency=currency,
                        source="local_csv",
                    ))
                except (ValueError, KeyError) as e:
                    warnings.append(f"row_{i}_skipped:{e}")
                    if len(warnings) > 50:
                        warnings.append("additional_row_errors_suppressed")
                        break
        return bars, warnings

    def _load_jsonl(
        self,
        path: Path,
        *,
        default_instrument: str,
        timeframe: str,
        currency: str,
        date_range: tuple[float, float] | None,
        max_rows: int,
    ) -> tuple[list[AdjustedPriceBar], list[str]]:
        warnings: list[str] = []
        bars: list[AdjustedPriceBar] = []
        with path.open("r", encoding="utf-8") as f:
            for i, line in enumerate(f):
                if i >= max_rows:
                    warnings.append(f"truncated_at_max_rows:{max_rows}")
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                    ts = float(row.get("ts") or row.get("timestamp") or 0)
                    if not ts and row.get("date"):
                        ts = _parse_ts(str(row["date"]))
                    if date_range and not (date_range[0] <= ts <= date_range[1]):
                        continue
                    inst = str(row.get("instrument") or row.get("symbol") or default_instrument).upper()
                    o, h, l, c = _dec(row["open"]), _dec(row["high"]), _dec(row["low"]), _dec(row["close"])
                    v = _dec(row.get("volume", 0))
                    bars.append(AdjustedPriceBar(
                        instrument=inst, ts=ts,
                        open=o, high=h, low=l, close=c, volume=v,
                        adj_open=o, adj_high=h, adj_low=l, adj_close=c,
                        timeframe=timeframe, currency=currency, source="local_jsonl",
                    ))
                except Exception as e:
                    warnings.append(f"line_{i}_skipped:{e}")
        return bars, warnings

    def _load_parquet(
        self,
        path: Path,
        *,
        default_instrument: str,
        timeframe: str,
        currency: str,
        schema_map: dict[str, str] | None,
        date_range: tuple[float, float] | None,
        max_rows: int,
    ) -> tuple[list[AdjustedPriceBar], list[str]]:
        """Parquet via pyarrow if available; else fail closed with clear error."""
        try:
            import pyarrow.parquet as pq  # type: ignore
        except ImportError:
            # Fallback: reject rather than invent data
            raise ValueError(
                "parquet_requires_pyarrow — install pyarrow or convert to CSV"
            )
        table = pq.read_table(path)
        if table.num_rows > max_rows:
            table = table.slice(0, max_rows)
        cols = {c: table.column(c).to_pylist() for c in table.column_names}
        headers = list(table.column_names)
        mapping = _map_headers(headers, schema_map)
        required = {"timestamp", "open", "high", "low", "close"}
        if not required.issubset(mapping.keys()):
            raise ValueError(f"schema_missing_fields:{sorted(required - set(mapping))}")
        n = table.num_rows
        bars: list[AdjustedPriceBar] = []
        warnings: list[str] = []
        for i in range(n):
            try:
                raw_ts = cols[mapping["timestamp"]][i]
                if isinstance(raw_ts, (int, float)):
                    ts = float(raw_ts)
                    # ms epoch heuristic
                    if ts > 1e12:
                        ts = ts / 1000.0
                else:
                    ts = _parse_ts(str(raw_ts))
                if date_range and not (date_range[0] <= ts <= date_range[1]):
                    continue
                inst_col = mapping.get("instrument")
                inst = str(cols[inst_col][i] if inst_col else default_instrument).upper()
                o = _dec(cols[mapping["open"]][i])
                h = _dec(cols[mapping["high"]][i])
                l = _dec(cols[mapping["low"]][i])
                c = _dec(cols[mapping["close"]][i])
                vol_col = mapping.get("volume")
                v = _dec(cols[vol_col][i] if vol_col else 0)
                bars.append(AdjustedPriceBar(
                    instrument=inst, ts=ts,
                    open=o, high=h, low=l, close=c, volume=v,
                    adj_open=o, adj_high=h, adj_low=l, adj_close=c,
                    timeframe=timeframe, currency=currency, source="local_parquet",
                ))
            except Exception as e:
                warnings.append(f"row_{i}_skipped:{e}")
        return bars, warnings
