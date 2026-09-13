"""M — OWNER_NEPSE_EOD_IMPORT — canonical ingestion of an OWNER-SUPPLIED official
NEPSE EOD export.

The owner manually downloads the official export in their own authenticated browser;
SaathiOS parses a LOCAL file only. NOT web scraping, browser automation, token
extraction, Browser Use, or Agent Reach. Provenance is established (owner attestation)
BEFORE any canonical write. This module is the ONLY canonical md_bars write path for
owner imports; Research/Agent-Reach/Browser-Use/Catalyst/chat/voice cannot write bars.

Point-in-time: md_bars has source_epoch/ingest_epoch but no available_at column, so we
store the conservative availability boundary in source_epoch and record provenance +
availability in additive tables (md_owner_import_run, md_bar_source). No new bar schema,
store, symbol registry, calendar, or provider hierarchy is created.
"""
from __future__ import annotations

import csv
import hashlib
import io
import time
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
from pathlib import Path

from saathi.platform.market_data.models import MDBar, MarketDataQuality, Timeframe
from saathi.platform.market_data.store import MarketDataStore
from saathi.platform.nepse.instruments import instrument_id_for, normalize_symbol

PROVIDER = "nepse_owner_import"
SOURCE_CLAIM_DEFAULT = "NEPAL_STOCK_EXCHANGE"
MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_ROWS = 20_000


class Provenance(str, Enum):
    OFFICIAL_VERIFIED = "OFFICIAL_VERIFIED"        # owner-attested official download
    OFFICIAL_PLAUSIBLE = "OFFICIAL_PLAUSIBLE"
    UNVERIFIED = "UNVERIFIED"
    THIRD_PARTY = "THIRD_PARTY"
    TAMPERED_OR_INVALID = "TAMPERED_OR_INVALID"


class ImportStatus(str, Enum):
    DRY_RUN = "DRY_RUN"
    IMPORTED = "IMPORTED"
    ALREADY_IMPORTED = "ALREADY_IMPORTED"
    INVALID_EXPORT_FORMAT = "INVALID_EXPORT_FORMAT"
    PROVENANCE_UNVERIFIED = "PROVENANCE_UNVERIFIED"
    NO_VALID_ROWS = "NO_VALID_ROWS"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    FILE_ERROR = "FILE_ERROR"


class DetectedFormat(str, Enum):
    CSV = "CSV"
    XLSX_UNSUPPORTED = "XLSX_UNSUPPORTED"    # detected but needs openpyxl (not installed)
    XLS_UNSUPPORTED = "XLS_UNSUPPORTED"
    HTML_MASQUERADE = "HTML_MASQUERADE"
    JSON_ERROR = "JSON_ERROR"
    EMPTY = "EMPTY"
    UNKNOWN = "UNKNOWN"


@dataclass
class OwnerArtifact:
    file_name: str
    file_size: int
    sha256: str
    received_at: float
    detected_format: DetectedFormat
    source_claim: str = SOURCE_CLAIM_DEFAULT
    verification_method: str = ""
    provenance: Provenance = Provenance.UNVERIFIED
    artifact_id: str = ""

    def as_dict(self) -> dict:
        return {"file_name": self.file_name, "file_size": self.file_size, "sha256": self.sha256,
                "received_at": self.received_at, "detected_format": self.detected_format.value,
                "source_claim": self.source_claim, "verification_method": self.verification_method,
                "provenance": self.provenance.value, "artifact_id": self.artifact_id}


@dataclass
class ImportResult:
    status: ImportStatus
    artifact: OwnerArtifact | None = None
    import_run_id: str = ""
    rows_seen: int = 0
    rows_valid: int = 0
    rows_rejected: int = 0
    rows_inserted: int = 0
    rows_unchanged: int = 0
    rows_revised: int = 0
    symbols_resolved: int = 0
    symbols_unresolved: int = 0
    earliest_trading_date: str = ""
    latest_trading_date: str = ""
    available_at_method: str = ""
    errors: list = field(default_factory=list)
    revisions: list = field(default_factory=list)
    limitations: list = field(default_factory=list)

    def as_dict(self) -> dict:
        d = {k: getattr(self, k) for k in (
            "import_run_id", "rows_seen", "rows_valid", "rows_rejected", "rows_inserted",
            "rows_unchanged", "rows_revised", "symbols_resolved", "symbols_unresolved",
            "earliest_trading_date", "latest_trading_date", "available_at_method")}
        d["status"] = self.status.value
        d["artifact"] = self.artifact.as_dict() if self.artifact else None
        d["errors"] = self.errors[:50]
        d["revisions"] = self.revisions[:50]
        d["limitations"] = list(self.limitations)
        return d


# ── format detection (magic, not extension) ──────────────────────────────────
def detect_format(data: bytes) -> DetectedFormat:
    if not data.strip():
        return DetectedFormat.EMPTY
    head = data[:512].lstrip()
    low = head[:64].lower()
    if head[:2] == b"PK":                       # zip container → xlsx/ods
        return DetectedFormat.XLSX_UNSUPPORTED
    if head[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":   # OLE2 → legacy xls
        return DetectedFormat.XLS_UNSUPPORTED
    if low.startswith(b"<!doctype html") or low.startswith(b"<html") or b"<head" in low:
        return DetectedFormat.HTML_MASQUERADE
    if low.startswith(b"{") and (b"error" in data[:200].lower() or b"unauthorized" in data[:200].lower()):
        return DetectedFormat.JSON_ERROR
    # CSV-ish: has a delimiter and printable text
    try:
        text = data[:4096].decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return DetectedFormat.UNKNOWN
    if ("," in text or "\t" in text or ";" in text) and "\n" in text:
        return DetectedFormat.CSV
    return DetectedFormat.UNKNOWN


# ── schema recognition (versioned, explicit; never guess OHLC) ────────────────
# NEPSE exports vary; match header cells case-insensitively by contains.
_COL_ALIASES = {
    "symbol": ("symbol", "scrip", "stock symbol", "ticker"),
    "date": ("business date", "as of", "date", "trade date", "trading date"),
    "open": ("open",),
    "high": ("high",),
    "low": ("low",),
    "close": ("close",),
    "ltp": ("ltp", "last traded price", "last price", "close price"),
    "volume": ("volume", "total traded quantity", "qty", "traded shares", "vol"),
    "turnover": ("turnover", "amount", "total traded value"),
}


def _map_columns(header: list[str]) -> dict[str, int]:
    idx: dict[str, int] = {}
    norm = [(i, (h or "").strip().lower()) for i, h in enumerate(header)]
    for field_name, aliases in _COL_ALIASES.items():
        for i, h in norm:
            if any(h == a or h.startswith(a) for a in aliases):
                idx.setdefault(field_name, i)
                break
    return idx


def _dec(v) -> Decimal | None:
    try:
        s = str(v).replace(",", "").strip()
        if s == "" or s in ("-", "N/A", "NA"):
            return None
        return Decimal(s)
    except (InvalidOperation, ValueError):
        return None


def _parse_date(v, default: date | None) -> date | None:
    s = str(v or "").strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d", "%b %d, %Y", "%d-%b-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return default


# ── additive provenance / point-in-time tables (base md_bars lacks these) ─────
_PROV_SCHEMA = """
CREATE TABLE IF NOT EXISTS md_owner_import_run (
    import_run_id TEXT PRIMARY KEY, artifact_id TEXT, sha256 TEXT, file_name TEXT,
    source_claim TEXT, verification_method TEXT, provenance TEXT, status TEXT,
    rows_seen INTEGER, rows_valid INTEGER, rows_rejected INTEGER, rows_inserted INTEGER,
    rows_unchanged INTEGER, rows_revised INTEGER, symbols_resolved INTEGER, symbols_unresolved INTEGER,
    earliest_trading_date TEXT, latest_trading_date TEXT, available_at_method TEXT,
    started_at REAL, completed_at REAL
);
CREATE TABLE IF NOT EXISTS md_bar_source (
    org_id TEXT, provider TEXT, instrument TEXT, timeframe TEXT, start_epoch REAL,
    available_at REAL, import_run_id TEXT, artifact_id TEXT, sha256 TEXT,
    PRIMARY KEY (org_id, provider, instrument, timeframe, start_epoch)
);
CREATE TABLE IF NOT EXISTS md_bar_revision (
    id INTEGER PRIMARY KEY AUTOINCREMENT, org_id TEXT, instrument TEXT, timeframe TEXT,
    start_epoch REAL, old_close TEXT, new_close TEXT, old_artifact TEXT, new_artifact TEXT,
    detected_at REAL
);
"""


def _ensure_tables(store: MarketDataStore) -> None:
    store._conn.executescript(_PROV_SCHEMA)
    store._conn.commit()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _validate_ohlc(o, h, l, c, v) -> str:
    for name, x in (("open", o), ("high", h), ("low", l), ("close", c)):
        if x is None:
            return f"missing_{name}"     # never fabricate OHLC
        if x < 0:
            return f"negative_{name}"
    if v is not None and v < 0:
        return "negative_volume"
    if h < max(o, c, l) or l > min(o, c, h):
        return "invalid_ohlc_bounds"
    return ""


def _read_file(path: Path) -> tuple[bytes | None, str]:
    try:
        if not path.is_file():
            return None, "not_a_file"
        size = path.stat().st_size
        if size > MAX_FILE_BYTES:
            return None, "file_too_large"
        return path.read_bytes(), ""
    except Exception as e:
        return None, f"read_error:{type(e).__name__}"


def run_import(path: str | Path, *, store: MarketDataStore, org_id: str = "owner",
               dry_run: bool = True, attest_official: bool = False,
               source_claim: str = SOURCE_CLAIM_DEFAULT, trading_date: str = "",
               acquisition_method: str = "", now: float | None = None) -> ImportResult:
    """Inspect (dry_run=True, default) or canonically import a NEPSE export.

    Canonical writes require verified provenance: either attest_official=True (owner
    manual attestation) OR acquisition_method='OFFICIAL_BROWSER_DOWNLOAD' (automated
    governed Playwright download of the official export). Both yield OFFICIAL_VERIFIED.
    """
    verified = attest_official or acquisition_method == "OFFICIAL_BROWSER_DOWNLOAD"
    now = now if now is not None else time.time()
    p = Path(path)
    data, err = _read_file(p)
    if data is None:
        st = ImportStatus.FILE_TOO_LARGE if err == "file_too_large" else ImportStatus.FILE_ERROR
        return ImportResult(status=st, errors=[err])

    sha = _sha256(data)
    fmt = detect_format(data)
    vmethod = ("OFFICIAL_BROWSER_DOWNLOAD" if acquisition_method == "OFFICIAL_BROWSER_DOWNLOAD"
               else ("OWNER_ATTESTED_OFFICIAL_DOWNLOAD" if attest_official else ""))
    artifact = OwnerArtifact(
        file_name=p.name, file_size=len(data), sha256=sha, received_at=now,
        detected_format=fmt, source_claim=source_claim, verification_method=vmethod,
        provenance=Provenance.OFFICIAL_VERIFIED if verified else Provenance.UNVERIFIED,
        artifact_id=f"art_{sha[:16]}")
    res = ImportResult(status=ImportStatus.DRY_RUN, artifact=artifact,
                       available_at_method="AVAILABLE_AT_CONSERVATIVE_RETRIEVAL_BOUNDARY")

    if fmt != DetectedFormat.CSV:
        res.status = ImportStatus.INVALID_EXPORT_FORMAT
        res.errors.append(f"unsupported_or_invalid_format:{fmt.value}")
        if fmt in (DetectedFormat.XLSX_UNSUPPORTED, DetectedFormat.XLS_UNSUPPORTED):
            res.limitations.append("XLS/XLSX not supported (no openpyxl dep) — export as CSV")
        return res

    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        text = data.decode("latin-1", errors="replace")
    reader = csv.reader(io.StringIO(text))
    rows = [r for r in reader if any((c or "").strip() for c in r)]
    if len(rows) < 2:
        res.status = ImportStatus.NO_VALID_ROWS
        res.errors.append("empty_or_headerless")
        return res
    if len(rows) - 1 > MAX_ROWS:
        res.status = ImportStatus.INVALID_EXPORT_FORMAT
        res.errors.append(f"too_many_rows:{len(rows)-1}")
        return res

    cols = _map_columns(rows[0])
    if "symbol" not in cols or not ({"close", "ltp"} & set(cols)):
        res.status = ImportStatus.INVALID_EXPORT_FORMAT
        res.errors.append(f"missing_required_columns; detected={sorted(cols)}")
        return res
    default_dt = _parse_date(trading_date, None) if trading_date else None

    tf = Timeframe.D1
    bars: list[tuple[str, MDBar, date]] = []
    for rn, row in enumerate(rows[1:], start=2):
        res.rows_seen += 1
        def cell(f):
            i = cols.get(f)
            return row[i] if i is not None and i < len(row) else ""
        raw_sym = cell("symbol")
        # CSV formula-injection guard: a cell beginning with a formula trigger is
        # data, never executed — and never a valid NEPSE symbol.
        if str(raw_sym).lstrip()[:1] in ("=", "+", "-", "@", "\t"):
            res.symbols_unresolved += 1
            res.errors.append(f"row{rn}:SYMBOL_UNRESOLVED:formula_injection_guard:{raw_sym!r}")
            continue
        try:
            sym = normalize_symbol(raw_sym)
        except Exception:
            res.symbols_unresolved += 1
            res.errors.append(f"row{rn}:SYMBOL_UNRESOLVED:{raw_sym!r}")
            continue
        d = _parse_date(cell("date"), default_dt)
        if d is None:
            res.rows_rejected += 1
            res.errors.append(f"row{rn}:missing_trading_date (supply --trading-date if export has none)")
            continue
        o, h, l = _dec(cell("open")), _dec(cell("high")), _dec(cell("low"))
        c = _dec(cell("close")) if cols.get("close") is not None else _dec(cell("ltp"))
        v = _dec(cell("volume"))
        bad = _validate_ohlc(o, h, l, c, v)
        if bad:
            res.rows_rejected += 1
            res.errors.append(f"row{rn}:{bad}")
            continue
        res.symbols_resolved += 1
        res.rows_valid += 1
        start = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
        bar = MDBar(instrument=instrument_id_for(sym), timeframe=tf, provider=PROVIDER,
                    open=o, high=h, low=l, close=c, volume=(v if v is not None else Decimal(0)),
                    start_time=start,
                    end_time=datetime(d.year, d.month, d.day, tzinfo=timezone.utc).replace(hour=23, minute=59),
                    source_time=datetime.fromtimestamp(now, tz=timezone.utc),   # conservative available_at
                    ingested_at=datetime.fromtimestamp(now, tz=timezone.utc),
                    quality=MarketDataQuality.VALID)
        bars.append((sym, bar, d))

    if bars:
        ds = sorted(d for _, _, d in bars)
        res.earliest_trading_date, res.latest_trading_date = ds[0].isoformat(), ds[-1].isoformat()
    if not res.rows_valid:
        res.status = ImportStatus.NO_VALID_ROWS
        return res

    # provenance gate — only OFFICIAL_VERIFIED (owner attestation OR official browser
    # download) writes canonically
    if not verified:
        res.status = ImportStatus.DRY_RUN if dry_run else ImportStatus.PROVENANCE_UNVERIFIED
        res.limitations.append("provenance UNVERIFIED — owner attestation or official browser download required")
        return res
    if dry_run:
        res.status = ImportStatus.DRY_RUN
        return res

    # ── canonical write (the ONLY owner-import write path) ────────────────────
    _ensure_tables(store)
    # whole-file idempotency
    prior = store._conn.execute(
        "SELECT status FROM md_owner_import_run WHERE sha256=? AND status='IMPORTED'", (sha,)).fetchone()
    if prior:
        res.status = ImportStatus.ALREADY_IMPORTED
        res.limitations.append("identical artifact already imported (noop)")
        return res

    run_id = f"imp_{uuid.uuid4().hex[:12]}"
    for sym, bar, d in bars:
        start_epoch = bar.start_time.timestamp()
        existing = store._conn.execute(
            "SELECT close FROM md_bars WHERE org_id=? AND provider=? AND instrument=? AND timeframe=? AND start_epoch=?",
            (org_id, PROVIDER, bar.instrument, tf.value, start_epoch)).fetchone()
        outcome = store.insert_bar(org_id, bar, raw_hash=sha)
        if outcome == "inserted":
            res.rows_inserted += 1
        else:  # duplicate PK → md_bars keeps original (no silent overwrite)
            old_close = existing["close"] if existing else ""
            if existing and str(old_close) != str(bar.close):
                res.rows_revised += 1
                res.revisions.append({"symbol": sym, "date": d.isoformat(),
                                      "old_close": str(old_close), "new_close": str(bar.close)})
                store._conn.execute(
                    "INSERT INTO md_bar_revision(org_id,instrument,timeframe,start_epoch,old_close,new_close,old_artifact,new_artifact,detected_at)"
                    " VALUES(?,?,?,?,?,?,?,?,?)",
                    (org_id, bar.instrument, tf.value, start_epoch, str(old_close), str(bar.close), "", artifact.artifact_id, now))
            else:
                res.rows_unchanged += 1
        store._conn.execute(
            "INSERT OR IGNORE INTO md_bar_source(org_id,provider,instrument,timeframe,start_epoch,available_at,import_run_id,artifact_id,sha256)"
            " VALUES(?,?,?,?,?,?,?,?,?)",
            (org_id, PROVIDER, bar.instrument, tf.value, start_epoch, bar.source_time.timestamp(), run_id, artifact.artifact_id, sha))
    res.import_run_id = run_id
    res.status = ImportStatus.IMPORTED
    store._conn.execute(
        "INSERT INTO md_owner_import_run(import_run_id,artifact_id,sha256,file_name,source_claim,verification_method,provenance,status,"
        "rows_seen,rows_valid,rows_rejected,rows_inserted,rows_unchanged,rows_revised,symbols_resolved,symbols_unresolved,"
        "earliest_trading_date,latest_trading_date,available_at_method,started_at,completed_at)"
        " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (run_id, artifact.artifact_id, sha, artifact.file_name, source_claim, artifact.verification_method,
         artifact.provenance.value, res.status.value, res.rows_seen, res.rows_valid, res.rows_rejected,
         res.rows_inserted, res.rows_unchanged, res.rows_revised, res.symbols_resolved, res.symbols_unresolved,
         res.earliest_trading_date, res.latest_trading_date, res.available_at_method, now, time.time()))
    store._conn.commit()
    return res


# ── canonical point-in-time reader for the Catalyst Engine (read-only) ────────
def canonical_bar_reader(store: MarketDataStore, *, org_id: str = "owner"):
    """Return reader(symbol)->[{available_at, close, volume, session_date}] from canonical
    md_bars (available_at from md_bar_source; falls back to source_epoch). No writes."""
    _ensure_tables(store)

    def reader(symbol: str):
        try:
            inst = instrument_id_for(symbol)
        except Exception:
            return []
        rows = store.query_bars(org_id, inst, Timeframe.D1, 0.0, 9_999_999_999.0, limit=5000)
        out = []
        for r in rows:
            se = r["start_epoch"]
            av = store._conn.execute(
                "SELECT available_at FROM md_bar_source WHERE org_id=? AND instrument=? AND timeframe=? AND start_epoch=?",
                (org_id, inst, Timeframe.D1.value, se)).fetchone()
            available_at = (av["available_at"] if av else r.get("source_epoch", se))
            out.append({"available_at": float(available_at), "close": r["close"],
                        "volume": r["volume"],
                        "session_date": datetime.fromtimestamp(se, tz=timezone.utc).date().isoformat()})
        return out
    return reader


def import_health(store: MarketDataStore, *, org_id: str = "owner") -> dict:
    _ensure_tables(store)
    runs = store._conn.execute(
        "SELECT * FROM md_owner_import_run WHERE status='IMPORTED' ORDER BY completed_at DESC LIMIT 1").fetchone()
    nbars = store._conn.execute(
        "SELECT COUNT(*) n, MAX(start_epoch) mx FROM md_bars WHERE org_id=? AND provider=?",
        (org_id, PROVIDER)).fetchone()
    n = nbars["n"] if nbars else 0
    latest_dt = (datetime.fromtimestamp(nbars["mx"], tz=timezone.utc).date().isoformat()
                 if nbars and nbars["mx"] else "")
    status = "CANONICAL_DATA_AVAILABLE" if n else "NO_CANONICAL_DATA"
    return {
        "status": status, "source_kind": "OWNER_MANUAL_IMPORT (not a live feed)",
        "provider": PROVIDER, "canonical_bar_count": n, "latest_trading_date": latest_dt,
        "last_import": (dict(runs) if runs else None),
        "limitations": ["manual owner import; availability is conservative retrieval boundary"],
    }
