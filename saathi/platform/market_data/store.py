"""M62.2 — bounded single-host SQLite market-data store.

Persists instruments, bars, quotes, and rejected-record evidence. Tenant-scoped by
org_id. Idempotent ingestion via a unique (org, provider, instrument, timeframe,
start_epoch) constraint. Not multi-node safe; distributed ingestion is DISABLED.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time as _time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from saathi.platform.market_data.models import MDInstrument, MDBar, MDQuote, Timeframe, MarketDataQuality
from saathi.platform.trading_models import AssetClass

_SCHEMA = """
CREATE TABLE IF NOT EXISTS md_instruments (
    org_id TEXT NOT NULL, provider TEXT NOT NULL, canonical_symbol TEXT NOT NULL,
    venue TEXT NOT NULL DEFAULT '', symbol TEXT NOT NULL DEFAULT '',
    asset_class TEXT NOT NULL DEFAULT 'EQUITY', base_currency TEXT NOT NULL DEFAULT 'USD',
    quote_currency TEXT NOT NULL DEFAULT 'USD', price_precision INTEGER NOT NULL DEFAULT 2,
    quantity_precision INTEGER NOT NULL DEFAULT 0, timezone TEXT NOT NULL DEFAULT 'UTC',
    market_calendar TEXT NOT NULL DEFAULT 'DEFAULT_24_5', status TEXT NOT NULL DEFAULT 'active',
    updated_at REAL NOT NULL,
    PRIMARY KEY (org_id, provider, canonical_symbol)
);
CREATE TABLE IF NOT EXISTS md_bars (
    org_id TEXT NOT NULL, provider TEXT NOT NULL, instrument TEXT NOT NULL,
    timeframe TEXT NOT NULL, start_epoch REAL NOT NULL, end_epoch REAL NOT NULL,
    open TEXT NOT NULL, high TEXT NOT NULL, low TEXT NOT NULL, close TEXT NOT NULL, volume TEXT NOT NULL,
    source_epoch REAL NOT NULL, ingest_epoch REAL NOT NULL, quality TEXT NOT NULL,
    raw_hash TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (org_id, provider, instrument, timeframe, start_epoch)
);
CREATE TABLE IF NOT EXISTS md_quotes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    org_id TEXT NOT NULL, provider TEXT NOT NULL, instrument TEXT NOT NULL,
    bid TEXT NOT NULL, ask TEXT NOT NULL, last TEXT NOT NULL,
    source_epoch REAL NOT NULL, ingest_epoch REAL NOT NULL, quality TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS md_rejects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    org_id TEXT NOT NULL, provider TEXT NOT NULL, instrument TEXT NOT NULL,
    kind TEXT NOT NULL, quality TEXT NOT NULL, start_epoch REAL NOT NULL DEFAULT 0,
    raw_hash TEXT NOT NULL DEFAULT '', findings TEXT NOT NULL DEFAULT '[]', ingest_epoch REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_md_bars_q ON md_bars(org_id, instrument, timeframe, start_epoch);
CREATE INDEX IF NOT EXISTS idx_md_quotes_q ON md_quotes(org_id, instrument, ingest_epoch DESC);
"""


class MarketDataStore:
    def __init__(self, db_path: str | Path | None = None):
        env = os.environ.get("SAATHI_MARKETDATA_DB") or os.environ.get("SAATHI_PLATFORM_DB", "")
        default = Path(__file__).resolve().parents[3] / "data" / "platform" / "platform.db"
        self.db_path = Path(db_path) if db_path else (Path(env) if env else default)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # ── instruments ──────────────────────────────────────────────────────
    def upsert_instrument(self, org_id: str, inst: MDInstrument) -> None:
        self._conn.execute(
            "INSERT INTO md_instruments (org_id, provider, canonical_symbol, venue, symbol, asset_class,"
            " base_currency, quote_currency, price_precision, quantity_precision, timezone, market_calendar,"
            " status, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(org_id, provider, canonical_symbol) DO UPDATE SET venue=excluded.venue,"
            " symbol=excluded.symbol, asset_class=excluded.asset_class, timezone=excluded.timezone,"
            " market_calendar=excluded.market_calendar, status=excluded.status, updated_at=excluded.updated_at",
            (org_id, inst.provider, inst.canonical_symbol, inst.venue, inst.symbol, inst.asset_class.value,
             inst.base_currency, inst.quote_currency, inst.price_precision, inst.quantity_precision,
             inst.timezone, inst.market_calendar, inst.status, _time.time()),
        )
        self._conn.commit()

    def list_instruments(self, org_id: str, *, limit: int = 200) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM md_instruments WHERE org_id=? ORDER BY canonical_symbol LIMIT ?",
            (org_id, int(limit)),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_instrument(self, org_id: str, symbol: str) -> dict | None:
        r = self._conn.execute(
            "SELECT * FROM md_instruments WHERE org_id=? AND canonical_symbol=? LIMIT 1",
            (org_id, symbol),
        ).fetchone()
        return dict(r) if r else None

    # ── bars (idempotent) ────────────────────────────────────────────────
    def insert_bar(self, org_id: str, bar: MDBar, *, raw_hash: str = "") -> str:
        """Returns 'inserted' or 'duplicate' (idempotent on the unique key)."""
        cur = self._conn.execute(
            "INSERT OR IGNORE INTO md_bars (org_id, provider, instrument, timeframe, start_epoch, end_epoch,"
            " open, high, low, close, volume, source_epoch, ingest_epoch, quality, raw_hash)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (org_id, bar.provider, bar.instrument, bar.timeframe.value, bar.start_time.timestamp(),
             bar.end_time.timestamp(), str(bar.open), str(bar.high), str(bar.low), str(bar.close),
             str(bar.volume), bar.source_time.timestamp(), bar.ingested_at.timestamp(),
             bar.quality.value, raw_hash),
        )
        self._conn.commit()
        return "inserted" if cur.rowcount else "duplicate"

    def query_bars(self, org_id: str, instrument: str, timeframe: Timeframe,
                   start_epoch: float, end_epoch: float, *, limit: int = 1000) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM md_bars WHERE org_id=? AND instrument=? AND timeframe=?"
            " AND start_epoch>=? AND start_epoch<=? ORDER BY start_epoch ASC LIMIT ?",
            (org_id, instrument, timeframe.value, start_epoch, end_epoch, int(limit)),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── quotes ───────────────────────────────────────────────────────────
    def insert_quote(self, org_id: str, q: MDQuote) -> None:
        self._conn.execute(
            "INSERT INTO md_quotes (org_id, provider, instrument, bid, ask, last, source_epoch, ingest_epoch, quality)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (org_id, q.provider, q.instrument, str(q.bid), str(q.ask), str(q.last),
             q.source_time.timestamp(), q.ingested_at.timestamp(), q.quality.value),
        )
        self._conn.commit()

    def latest_quote(self, org_id: str, instrument: str) -> dict | None:
        r = self._conn.execute(
            "SELECT * FROM md_quotes WHERE org_id=? AND instrument=? ORDER BY ingest_epoch DESC LIMIT 1",
            (org_id, instrument),
        ).fetchone()
        return dict(r) if r else None

    # ── rejected-record evidence ─────────────────────────────────────────
    def record_reject(self, org_id: str, *, provider: str, instrument: str, kind: str,
                      quality: str, start_epoch: float = 0, raw_hash: str = "",
                      findings: list | None = None) -> None:
        self._conn.execute(
            "INSERT INTO md_rejects (org_id, provider, instrument, kind, quality, start_epoch, raw_hash, findings, ingest_epoch)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (org_id, provider, instrument, kind, quality, start_epoch, raw_hash,
             json.dumps(findings or []), _time.time()),
        )
        self._conn.commit()

    def count_rejects(self, org_id: str, instrument: str) -> int:
        r = self._conn.execute(
            "SELECT COUNT(*) c FROM md_rejects WHERE org_id=? AND instrument=?", (org_id, instrument)
        ).fetchone()
        return int(r["c"]) if r else 0
