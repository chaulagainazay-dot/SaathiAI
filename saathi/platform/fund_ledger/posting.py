"""OMS fill → ledger posting with pending/retry semantics (no silent diverge)."""
from __future__ import annotations

import json
import sqlite3
import threading
import time as _time
from pathlib import Path
from typing import Any

from saathi.platform.fund_ledger.cutover import fund_id_for_account
from saathi.platform.fund_ledger.paper_bridge import post_paper_fill_to_ledger
from saathi.platform.fund_ledger.reducer import LedgerError
from saathi.platform.fund_ledger.service import PortfolioLedgerService

POST_PENDING = "PENDING"
POST_POSTED = "POSTED"
POST_FAILED = "FAILED"
POST_DUPLICATE = "DUPLICATE"


_POST_SCHEMA = """
CREATE TABLE IF NOT EXISTS fl_account_bind (
    account_id TEXT PRIMARY KEY,
    fund_id TEXT NOT NULL UNIQUE,
    org_id TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS fl_fill_posts (
    fill_id TEXT PRIMARY KEY,
    fund_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    order_id TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL,
    ledger_event_id TEXT NOT NULL DEFAULT '',
    idempotency_key TEXT NOT NULL DEFAULT '',
    error TEXT NOT NULL DEFAULT '',
    attempts INTEGER NOT NULL DEFAULT 0,
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fl_fill_posts_status ON fl_fill_posts(status);
"""


class FillPostingStore:
    """Tracks OMS fill → ledger post outcomes (same process DB as fund ledger preferred)."""

    def __init__(self, path: str | Path | None = None, conn: sqlite3.Connection | None = None):
        self._lock = threading.RLock()
        if conn is not None:
            self._conn = conn
            self._own = False
        else:
            self.path = str(path) if path else ":memory:"
            self._conn = sqlite3.connect(self.path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._own = True
        self._conn.executescript(_POST_SCHEMA)
        self._conn.commit()

    def bind_account(self, account_id: str, fund_id: str, org_id: str = "") -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO fl_account_bind(account_id,fund_id,org_id,created_at) VALUES(?,?,?,?)",
                (account_id, fund_id, org_id, _time.time()),
            )
            self._conn.commit()

    def fund_for_account(self, account_id: str) -> str | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT fund_id FROM fl_account_bind WHERE account_id=?", (account_id,)
            ).fetchone()
        return row["fund_id"] if row else None

    def record_attempt(
        self,
        *,
        fill_id: str,
        fund_id: str,
        account_id: str,
        order_id: str,
        status: str,
        ledger_event_id: str = "",
        idempotency_key: str = "",
        error: str = "",
        payload: dict | None = None,
    ) -> None:
        now = _time.time()
        with self._lock:
            existing = self._conn.execute(
                "SELECT attempts FROM fl_fill_posts WHERE fill_id=?", (fill_id,)
            ).fetchone()
            attempts = int(existing["attempts"]) + 1 if existing else 1
            self._conn.execute(
                """INSERT INTO fl_fill_posts(
                    fill_id,fund_id,account_id,order_id,status,ledger_event_id,idempotency_key,
                    error,attempts,payload_json,created_at,updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(fill_id) DO UPDATE SET
                    status=excluded.status,
                    ledger_event_id=excluded.ledger_event_id,
                    error=excluded.error,
                    attempts=excluded.attempts,
                    updated_at=excluded.updated_at
                """,
                (
                    fill_id,
                    fund_id,
                    account_id,
                    order_id,
                    status,
                    ledger_event_id,
                    idempotency_key,
                    error[:500],
                    attempts,
                    json.dumps(payload or {}, sort_keys=True, default=str),
                    now,
                    now,
                ),
            )
            self._conn.commit()

    def get_post(self, fill_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM fl_fill_posts WHERE fill_id=?", (fill_id,)
            ).fetchone()
        return dict(row) if row else None

    def list_pending(self, limit: int = 100) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM fl_fill_posts WHERE status IN ('PENDING','FAILED') ORDER BY created_at ASC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def pending_count(self, account_id: str | None = None) -> int:
        with self._lock:
            if account_id:
                row = self._conn.execute(
                    "SELECT COUNT(*) AS c FROM fl_fill_posts WHERE account_id=? AND status IN ('PENDING','FAILED')",
                    (account_id,),
                ).fetchone()
            else:
                row = self._conn.execute(
                    "SELECT COUNT(*) AS c FROM fl_fill_posts WHERE status IN ('PENDING','FAILED')"
                ).fetchone()
        return int(row["c"])


def post_accepted_fill(
    ledger: PortfolioLedgerService,
    posts: FillPostingStore,
    *,
    account_id: str,
    fill_id: str,
    order_id: str,
    side: str,
    symbol: str,
    quantity: Any,
    price: Any,
    fee: Any = "0",
    actor: str = "paper_oms",
) -> dict:
    """Post one accepted OMS fill. Idempotent. Never raises to erase OMS fill.

    Returns status dict. On failure records PENDING/FAILED for retry.
    """
    fund_id = posts.fund_for_account(account_id) or fund_id_for_account(account_id)
    payload = {
        "fill_id": fill_id,
        "order_id": order_id,
        "side": side,
        "symbol": symbol,
        "quantity": str(quantity),
        "price": str(price),
        "fee": str(fee),
    }
    # already posted?
    prior = posts.get_post(fill_id)
    if prior and prior.get("status") in (POST_POSTED, POST_DUPLICATE) and prior.get("ledger_event_id"):
        return {
            "status": prior["status"],
            "fill_id": fill_id,
            "fund_id": fund_id,
            "ledger_event_id": prior.get("ledger_event_id"),
            "idempotent": True,
        }

    posts.record_attempt(
        fill_id=fill_id,
        fund_id=fund_id,
        account_id=account_id,
        order_id=order_id,
        status=POST_PENDING,
        idempotency_key=f"fill:{fill_id}",
        payload=payload,
    )
    try:
        result = post_paper_fill_to_ledger(
            ledger,
            fund_id,
            fill_id=fill_id,
            side=side,
            symbol=symbol,
            quantity=quantity,
            price=price,
            fee=fee,
            order_id=order_id,
            actor=actor,
        )
        st = result.get("status") or "ok"
        event_id = (result.get("event") or {}).get("event_id") or ""
        final = POST_DUPLICATE if st == "duplicate" else POST_POSTED
        posts.record_attempt(
            fill_id=fill_id,
            fund_id=fund_id,
            account_id=account_id,
            order_id=order_id,
            status=final,
            ledger_event_id=event_id,
            idempotency_key=f"fill:{fill_id}",
            payload=payload,
        )
        return {
            "status": final,
            "fill_id": fill_id,
            "fund_id": fund_id,
            "ledger_event_id": event_id,
            "ledger_status": st,
            "state": result.get("state"),
        }
    except Exception as e:  # noqa: BLE001 — must not unwind OMS fill
        posts.record_attempt(
            fill_id=fill_id,
            fund_id=fund_id,
            account_id=account_id,
            order_id=order_id,
            status=POST_FAILED,
            error=str(e),
            idempotency_key=f"fill:{fill_id}",
            payload=payload,
        )
        return {
            "status": POST_FAILED,
            "fill_id": fill_id,
            "fund_id": fund_id,
            "error": str(e),
            "portfolio_status": "RECONCILIATION_REQUIRED",
        }


def retry_pending_posts(ledger: PortfolioLedgerService, posts: FillPostingStore, *, limit: int = 50) -> list[dict]:
    results = []
    for row in posts.list_pending(limit=limit):
        payload = json.loads(row.get("payload_json") or "{}")
        results.append(
            post_accepted_fill(
                ledger,
                posts,
                account_id=row["account_id"],
                fill_id=row["fill_id"],
                order_id=row.get("order_id") or "",
                side=payload.get("side") or "BUY",
                symbol=payload.get("symbol") or "",
                quantity=payload.get("quantity") or "0",
                price=payload.get("price") or "0",
                fee=payload.get("fee") or "0",
            )
        )
    return results
