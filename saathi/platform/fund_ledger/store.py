"""SQLite append-only event store for the canonical fund ledger."""
from __future__ import annotations

import json
import sqlite3
import threading
import time as _time
from pathlib import Path
from typing import Any

from saathi.platform.fund_ledger.models import Fund, LedgerEvent, Security

_SCHEMA = """
CREATE TABLE IF NOT EXISTS fl_funds (
    fund_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    base_currency TEXT NOT NULL DEFAULT 'USD',
    environment TEXT NOT NULL DEFAULT 'PAPER',
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS fl_securities (
    security_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    venue TEXT NOT NULL DEFAULT 'PAPER',
    asset_class TEXT NOT NULL DEFAULT 'EQUITY',
    currency TEXT NOT NULL DEFAULT 'USD',
    price_precision INTEGER NOT NULL DEFAULT 6,
    quantity_precision INTEGER NOT NULL DEFAULT 6
);
CREATE TABLE IF NOT EXISTS fl_events (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    fund_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    ts REAL NOT NULL,
    actor TEXT NOT NULL DEFAULT 'system',
    source TEXT NOT NULL DEFAULT 'paper',
    security_id TEXT NOT NULL DEFAULT '',
    symbol TEXT NOT NULL DEFAULT '',
    side TEXT NOT NULL DEFAULT '',
    quantity TEXT NOT NULL DEFAULT '0',
    price TEXT NOT NULL DEFAULT '0',
    fee TEXT NOT NULL DEFAULT '0',
    cash_delta TEXT NOT NULL DEFAULT '0',
    currency TEXT NOT NULL DEFAULT 'USD',
    fill_ref TEXT NOT NULL DEFAULT '',
    order_ref TEXT NOT NULL DEFAULT '',
    reason TEXT NOT NULL DEFAULT '',
    reverses_event_id TEXT NOT NULL DEFAULT '',
    payload_json TEXT NOT NULL DEFAULT '{}',
    idempotency_key TEXT NOT NULL,
    UNIQUE (fund_id, idempotency_key)
);
CREATE INDEX IF NOT EXISTS idx_fl_events_fund ON fl_events(fund_id, seq);
CREATE TABLE IF NOT EXISTS fl_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    fund_id TEXT NOT NULL,
    ts REAL NOT NULL,
    nav TEXT NOT NULL,
    cash TEXT NOT NULL,
    positions_value TEXT NOT NULL,
    realized_pnl TEXT NOT NULL,
    unrealized_pnl TEXT NOT NULL,
    event_count INTEGER NOT NULL,
    state_hash TEXT NOT NULL,
    state_json TEXT NOT NULL
);
"""


class DuplicateEventError(Exception):
    def __init__(self, event_id: str, idempotency_key: str):
        super().__init__(f"duplicate event {event_id} key={idempotency_key}")
        self.event_id = event_id
        self.idempotency_key = idempotency_key


class FundLedgerStore:
    """Thread-safe local SQLite store. Not multi-node."""

    def __init__(self, path: str | Path | None = None):
        self.path = str(path) if path else ":memory:"
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def create_fund(self, fund: Fund) -> Fund:
        with self._lock:
            self._conn.execute(
                "INSERT INTO fl_funds(fund_id,name,base_currency,environment,created_at) VALUES(?,?,?,?,?)",
                (fund.fund_id, fund.name, fund.base_currency, fund.environment, fund.created_at),
            )
            self._conn.commit()
        return fund

    def get_fund(self, fund_id: str) -> Fund | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM fl_funds WHERE fund_id=?", (fund_id,)).fetchone()
        if not row:
            return None
        return Fund(
            fund_id=row["fund_id"],
            name=row["name"],
            base_currency=row["base_currency"],
            environment=row["environment"],
            created_at=row["created_at"],
        )

    def upsert_security(self, sec: Security) -> Security:
        with self._lock:
            self._conn.execute(
                """INSERT INTO fl_securities(security_id,symbol,venue,asset_class,currency,price_precision,quantity_precision)
                   VALUES(?,?,?,?,?,?,?)
                   ON CONFLICT(security_id) DO UPDATE SET symbol=excluded.symbol""",
                (
                    sec.security_id,
                    sec.symbol,
                    sec.venue,
                    sec.asset_class,
                    sec.currency,
                    sec.price_precision,
                    sec.quantity_precision,
                ),
            )
            self._conn.commit()
        return sec

    def get_security(self, security_id: str) -> Security | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM fl_securities WHERE security_id=?", (security_id,)
            ).fetchone()
        if not row:
            return None
        return Security(
            security_id=row["security_id"],
            symbol=row["symbol"],
            venue=row["venue"],
            asset_class=row["asset_class"],
            currency=row["currency"],
            price_precision=row["price_precision"],
            quantity_precision=row["quantity_precision"],
        )

    def append_event(self, event: LedgerEvent) -> tuple[str, LedgerEvent]:
        """Append event. Returns ('ok', event) or raises DuplicateEventError.

        Idempotent: same (fund_id, idempotency_key) returns existing without re-apply
        at store layer — caller still treats as no-op.
        """
        rec = event.to_record()
        with self._lock:
            existing = self._conn.execute(
                "SELECT event_id FROM fl_events WHERE fund_id=? AND idempotency_key=?",
                (event.fund_id, rec["idempotency_key"]),
            ).fetchone()
            if existing:
                # Idempotent re-delivery: return prior event; do not double-apply.
                row = self._conn.execute(
                    "SELECT * FROM fl_events WHERE event_id=?", (existing["event_id"],)
                ).fetchone()
                return ("duplicate", self._row_to_event(row))
            try:
                self._conn.execute(
                    """INSERT INTO fl_events(
                        event_id,fund_id,event_type,ts,actor,source,security_id,symbol,side,
                        quantity,price,fee,cash_delta,currency,fill_ref,order_ref,reason,
                        reverses_event_id,payload_json,idempotency_key
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        rec["event_id"],
                        rec["fund_id"],
                        rec["event_type"],
                        rec["ts"],
                        rec["actor"],
                        rec["source"],
                        rec["security_id"],
                        rec["symbol"],
                        rec["side"],
                        rec["quantity"],
                        rec["price"],
                        rec["fee"],
                        rec["cash_delta"],
                        rec["currency"],
                        rec["fill_ref"],
                        rec["order_ref"],
                        rec["reason"],
                        rec["reverses_event_id"],
                        json.dumps(rec["payload"], sort_keys=True),
                        rec["idempotency_key"],
                    ),
                )
                self._conn.commit()
            except sqlite3.IntegrityError as e:
                raise DuplicateEventError(event.event_id, rec["idempotency_key"]) from e
        return ("ok", event)

    def list_events(self, fund_id: str) -> list[LedgerEvent]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM fl_events WHERE fund_id=? ORDER BY seq ASC", (fund_id,)
            ).fetchall()
        return [self._row_to_event(r) for r in rows]

    def save_snapshot(self, snapshot_id: str, fund_id: str, state_public: dict, state_hash: str) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT OR REPLACE INTO fl_snapshots(
                    snapshot_id,fund_id,ts,nav,cash,positions_value,realized_pnl,unrealized_pnl,
                    event_count,state_hash,state_json
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    snapshot_id,
                    fund_id,
                    float(state_public.get("ts") or _time.time()),
                    state_public.get("nav", "0"),
                    state_public.get("cash", "0"),
                    state_public.get("positions_value", "0"),
                    state_public.get("realized_pnl", "0"),
                    state_public.get("unrealized_pnl", "0"),
                    int(state_public.get("event_count") or 0),
                    state_hash,
                    json.dumps(state_public, sort_keys=True, default=str),
                ),
            )
            self._conn.commit()

    def _row_to_event(self, row: sqlite3.Row) -> LedgerEvent:
        payload = json.loads(row["payload_json"] or "{}")
        return LedgerEvent.from_record(
            {
                "event_id": row["event_id"],
                "fund_id": row["fund_id"],
                "event_type": row["event_type"],
                "ts": row["ts"],
                "actor": row["actor"],
                "source": row["source"],
                "security_id": row["security_id"],
                "symbol": row["symbol"],
                "side": row["side"],
                "quantity": row["quantity"],
                "price": row["price"],
                "fee": row["fee"],
                "cash_delta": row["cash_delta"],
                "currency": row["currency"],
                "fill_ref": row["fill_ref"],
                "order_ref": row["order_ref"],
                "reason": row["reason"],
                "reverses_event_id": row["reverses_event_id"],
                "payload": payload,
                "idempotency_key": row["idempotency_key"],
            }
        )
