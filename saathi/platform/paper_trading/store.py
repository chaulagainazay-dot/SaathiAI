"""M62.5 — single-host SQLite persistence for the paper broker.

Tenant-scoped by ``org_id``. Fills and terminal transitions are immutable. Mutations
that must reconcile (submission, fill accounting, cancellation) go through the
``persist_*`` methods, each of which runs in ONE atomic transaction — a failure
anywhere rolls the whole thing back, leaving no partial account mutation. Not
multi-node safe; distributed mode is not enabled.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time as _time
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable

from saathi.platform.models import new_id
from saathi.platform.trading_models import OrderSide, OrderType, TimeInForce, Environment
from saathi.platform.paper_trading.models import (
    PaperAccount, PaperPosition, PaperOrder, PaperFill, AccountStatus, BrokerOrderState, D, q2,
)


def _dumps(obj) -> str:
    return json.dumps(obj, default=str, sort_keys=True)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS paper_accounts (
    id TEXT PRIMARY KEY, org_id TEXT NOT NULL, workspace_id TEXT NOT NULL, project_id TEXT NOT NULL DEFAULT '',
    name TEXT NOT NULL, base_currency TEXT NOT NULL DEFAULT 'USD',
    starting_cash TEXT NOT NULL, current_cash TEXT NOT NULL, reserved_cash TEXT NOT NULL DEFAULT '0',
    realized_pnl TEXT NOT NULL DEFAULT '0', status TEXT NOT NULL DEFAULT 'DRAFT', environment TEXT NOT NULL DEFAULT 'PAPER',
    halt_reason TEXT NOT NULL DEFAULT '', created_by TEXT NOT NULL, created_at REAL NOT NULL,
    updated_at REAL NOT NULL, version INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS paper_positions (
    org_id TEXT NOT NULL, account_id TEXT NOT NULL, symbol TEXT NOT NULL,
    quantity TEXT NOT NULL DEFAULT '0', reserved_quantity TEXT NOT NULL DEFAULT '0',
    avg_cost TEXT NOT NULL DEFAULT '0', realized_pnl TEXT NOT NULL DEFAULT '0',
    PRIMARY KEY (account_id, symbol)
);
CREATE TABLE IF NOT EXISTS paper_intents (
    intent_id TEXT PRIMARY KEY, org_id TEXT NOT NULL, workspace_id TEXT NOT NULL, account_id TEXT NOT NULL,
    payload_json TEXT NOT NULL, guardian_json TEXT NOT NULL DEFAULT '{}', state TEXT NOT NULL DEFAULT 'DRAFT',
    reason TEXT NOT NULL DEFAULT '', correlation_id TEXT NOT NULL DEFAULT '', idempotency_key TEXT NOT NULL DEFAULT '',
    approval_id TEXT NOT NULL DEFAULT '', strategy_ref TEXT NOT NULL DEFAULT '', thesis_ref TEXT NOT NULL DEFAULT '',
    market_data_ref TEXT NOT NULL DEFAULT '', proposed_by TEXT NOT NULL DEFAULT '',
    version INTEGER NOT NULL DEFAULT 1, created_at REAL NOT NULL, updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS paper_orders (
    id TEXT PRIMARY KEY, org_id TEXT NOT NULL, order_intent_id TEXT NOT NULL, paper_account_id TEXT NOT NULL,
    symbol TEXT NOT NULL, side TEXT NOT NULL, order_type TEXT NOT NULL,
    original_quantity TEXT NOT NULL, filled_quantity TEXT NOT NULL DEFAULT '0',
    limit_price TEXT, time_in_force TEXT NOT NULL DEFAULT 'DAY', broker_state TEXT NOT NULL,
    rejection_reason TEXT NOT NULL DEFAULT '', idempotency_key TEXT NOT NULL DEFAULT '',
    reserved_cash TEXT NOT NULL DEFAULT '0', reserved_quantity TEXT NOT NULL DEFAULT '0',
    market_data_ref TEXT NOT NULL DEFAULT '', correlation_id TEXT NOT NULL DEFAULT '',
    submitted_at REAL NOT NULL, accepted_at REAL NOT NULL DEFAULT 0, cancelled_at REAL NOT NULL DEFAULT 0,
    completed_at REAL NOT NULL DEFAULT 0, version INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS paper_fills (
    id TEXT PRIMARY KEY, org_id TEXT NOT NULL, paper_order_id TEXT NOT NULL, event_ts REAL NOT NULL,
    quantity TEXT NOT NULL, price TEXT NOT NULL, gross_amount TEXT NOT NULL, fee TEXT NOT NULL,
    slippage TEXT NOT NULL DEFAULT '0', side TEXT NOT NULL, liquidity_ref TEXT NOT NULL DEFAULT '',
    market_data_ref TEXT NOT NULL DEFAULT '', fee_model_version TEXT NOT NULL DEFAULT '',
    slippage_model_version TEXT NOT NULL DEFAULT '', result_hash TEXT NOT NULL DEFAULT '',
    seq INTEGER NOT NULL DEFAULT 0, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS paper_transitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, org_id TEXT NOT NULL, paper_order_id TEXT NOT NULL,
    from_state TEXT NOT NULL, to_state TEXT NOT NULL, reason TEXT NOT NULL DEFAULT '',
    correlation_id TEXT NOT NULL DEFAULT '', ts REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS paper_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT, org_id TEXT NOT NULL, account_id TEXT NOT NULL, kind TEXT NOT NULL,
    amount TEXT NOT NULL, balance_after TEXT NOT NULL, reserved_after TEXT NOT NULL DEFAULT '0',
    ref TEXT NOT NULL DEFAULT '', note TEXT NOT NULL DEFAULT '', ts REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS paper_idempotency (
    org_id TEXT NOT NULL, scope TEXT NOT NULL, key TEXT NOT NULL, payload_hash TEXT NOT NULL,
    result_json TEXT NOT NULL, created_at REAL NOT NULL, PRIMARY KEY (org_id, scope, key)
);
CREATE TABLE IF NOT EXISTS paper_processed_events (
    org_id TEXT NOT NULL, paper_order_id TEXT NOT NULL, event_hash TEXT NOT NULL, ts REAL NOT NULL,
    PRIMARY KEY (paper_order_id, event_hash)
);
CREATE INDEX IF NOT EXISTS idx_pa_org ON paper_accounts(org_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_po_acct ON paper_orders(org_id, paper_account_id, submitted_at DESC);
CREATE INDEX IF NOT EXISTS idx_pf_order ON paper_fills(org_id, paper_order_id, seq);
CREATE INDEX IF NOT EXISTS idx_pi_acct ON paper_intents(org_id, account_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_pl_acct ON paper_ledger(org_id, account_id, ts);
CREATE UNIQUE INDEX IF NOT EXISTS idx_po_idem ON paper_orders(org_id, idempotency_key);
"""


class IdempotencyConflict(Exception):
    """Same key, different payload."""


class _LockedResult:
    """Result shim: SELECT rows AND lastrowid/rowcount are captured under the lock at
    execute time, so a concurrent thread cannot invalidate the cursor before fetch."""
    __slots__ = ("_rows", "lastrowid", "rowcount")

    def __init__(self, rows, lastrowid, rowcount):
        self._rows = rows
        self.lastrowid = lastrowid
        self.rowcount = rowcount

    def fetchall(self):
        return list(self._rows or [])

    def fetchone(self):
        return self._rows.pop(0) if self._rows else None


class _SerializedConn:
    """Thread-safe facade over one shared sqlite3 connection. ``execute`` serializes
    each statement AND (for SELECTs) its fetch under a single reentrant lock, so the
    connection can be used from FastAPI's threadpool without ``InterfaceError`` from
    interleaved cursors. Write blocks that hold ``with lock, conn:`` keep using the
    raw cursor and are unaffected (the lock is reentrant)."""

    def __init__(self, raw, lock):
        object.__setattr__(self, "_raw", raw)
        object.__setattr__(self, "_lock", lock)

    def execute(self, sql, params=()):
        with self._lock:
            cur = self._raw.execute(sql, params)
            rows = cur.fetchall() if cur.description is not None else None
            return _LockedResult(rows, cur.lastrowid, cur.rowcount)

    def executescript(self, script):
        with self._lock:
            return self._raw.executescript(script)

    def cursor(self):
        return self._raw.cursor()

    def commit(self):
        with self._lock:
            return self._raw.commit()

    def __enter__(self):
        return self._raw.__enter__()

    def __exit__(self, *a):
        return self._raw.__exit__(*a)

    def __getattr__(self, name):
        return getattr(self._raw, name)

    def __setattr__(self, name, value):
        setattr(self._raw, name, value)


class PaperStore:
    def __init__(self, db_path: str | Path | None = None):
        env = os.environ.get("SAATHI_PAPER_DB") or os.environ.get("SAATHI_PLATFORM_DB", "")
        default = Path(__file__).resolve().parents[3] / "data" / "platform" / "platform.db"
        self.db_path = Path(db_path) if db_path else (Path(env) if env else default)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        raw = sqlite3.connect(str(self.db_path), check_same_thread=False)
        raw.row_factory = sqlite3.Row
        raw.execute("PRAGMA foreign_keys=ON")
        raw.executescript(_SCHEMA)
        raw.commit()
        self._lock = threading.RLock()
        # Serialize all shared-connection access (reads materialized under the lock).
        # SafetyStore/ReconStore reuse this same wrapped connection + lock.
        self._conn = _SerializedConn(raw, self._lock)

    def _now(self) -> float:
        return _time.time()

    # ── serialization ────────────────────────────────────────────────────────
    @staticmethod
    def _acct(r: sqlite3.Row) -> PaperAccount:
        return PaperAccount(
            id=r["id"], org_id=r["org_id"], workspace_id=r["workspace_id"], project_id=r["project_id"],
            name=r["name"], base_currency=r["base_currency"], starting_cash=D(r["starting_cash"]),
            current_cash=D(r["current_cash"]), reserved_cash=D(r["reserved_cash"]), realized_pnl=D(r["realized_pnl"]),
            status=AccountStatus(r["status"]), environment=Environment(r["environment"]), created_by=r["created_by"],
            created_at=r["created_at"], updated_at=r["updated_at"], version=r["version"])

    @staticmethod
    def _pos(r: sqlite3.Row) -> PaperPosition:
        return PaperPosition(account_id=r["account_id"], symbol=r["symbol"], quantity=D(r["quantity"]),
                             reserved_quantity=D(r["reserved_quantity"]), avg_cost=D(r["avg_cost"]),
                             realized_pnl=D(r["realized_pnl"]))

    @staticmethod
    def _order(r: sqlite3.Row) -> PaperOrder:
        return PaperOrder(
            id=r["id"], order_intent_id=r["order_intent_id"], paper_account_id=r["paper_account_id"],
            org_id=r["org_id"], symbol=r["symbol"], side=OrderSide(r["side"]), order_type=OrderType(r["order_type"]),
            original_quantity=D(r["original_quantity"]), filled_quantity=D(r["filled_quantity"]),
            limit_price=D(r["limit_price"]) if r["limit_price"] is not None else None,
            time_in_force=TimeInForce(r["time_in_force"]), broker_state=BrokerOrderState(r["broker_state"]),
            rejection_reason=r["rejection_reason"], idempotency_key=r["idempotency_key"],
            reserved_cash=D(r["reserved_cash"]), reserved_quantity=D(r["reserved_quantity"]),
            market_data_ref=r["market_data_ref"], correlation_id=r["correlation_id"],
            submitted_at=r["submitted_at"], accepted_at=r["accepted_at"], cancelled_at=r["cancelled_at"],
            completed_at=r["completed_at"], version=r["version"])

    def _write_account(self, cur, a: PaperAccount, *, halt_reason: str = "") -> None:
        cur.execute(
            "INSERT OR REPLACE INTO paper_accounts (id,org_id,workspace_id,project_id,name,base_currency,"
            "starting_cash,current_cash,reserved_cash,realized_pnl,status,environment,halt_reason,created_by,"
            "created_at,updated_at,version) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (a.id, a.org_id, a.workspace_id, a.project_id, a.name, a.base_currency, str(a.starting_cash),
             str(a.current_cash), str(a.reserved_cash), str(a.realized_pnl), a.status.value, a.environment.value,
             halt_reason, a.created_by, a.created_at, self._now(), a.version))

    def _write_position(self, cur, p: PaperPosition, org_id: str) -> None:
        cur.execute(
            "INSERT OR REPLACE INTO paper_positions (org_id,account_id,symbol,quantity,reserved_quantity,"
            "avg_cost,realized_pnl) VALUES (?,?,?,?,?,?,?)",
            (org_id, p.account_id, p.symbol, str(p.quantity), str(p.reserved_quantity), str(p.avg_cost),
             str(p.realized_pnl)))

    def _write_order(self, cur, o: PaperOrder) -> None:
        cur.execute(
            "INSERT OR REPLACE INTO paper_orders (id,org_id,order_intent_id,paper_account_id,symbol,side,order_type,"
            "original_quantity,filled_quantity,limit_price,time_in_force,broker_state,rejection_reason,idempotency_key,"
            "reserved_cash,reserved_quantity,market_data_ref,correlation_id,submitted_at,accepted_at,cancelled_at,"
            "completed_at,version) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (o.id, o.org_id, o.order_intent_id, o.paper_account_id, o.symbol, o.side.value, o.order_type.value,
             str(o.original_quantity), str(o.filled_quantity),
             str(o.limit_price) if o.limit_price is not None else None, o.time_in_force.value, o.broker_state.value,
             o.rejection_reason, o.idempotency_key, str(o.reserved_cash), str(o.reserved_quantity),
             o.market_data_ref, o.correlation_id, o.submitted_at, o.accepted_at, o.cancelled_at, o.completed_at,
             o.version))

    def _write_transition(self, cur, org_id, order_id, frm, to, reason, corr) -> None:
        cur.execute("INSERT INTO paper_transitions (org_id,paper_order_id,from_state,to_state,reason,correlation_id,ts)"
                    " VALUES (?,?,?,?,?,?,?)", (org_id, order_id, frm, to, reason, corr, self._now()))

    def _write_ledger(self, cur, org_id, account_id, kind, amount, balance_after, reserved_after, ref, note) -> None:
        cur.execute("INSERT INTO paper_ledger (org_id,account_id,kind,amount,balance_after,reserved_after,ref,note,ts)"
                    " VALUES (?,?,?,?,?,?,?,?,?)",
                    (org_id, account_id, kind, str(amount), str(balance_after), str(reserved_after), ref, note, self._now()))

    # ── accounts ──────────────────────────────────────────────────────────────
    def create_account(self, a: PaperAccount) -> PaperAccount:
        with self._lock, self._conn:
            self._write_account(self._conn, a)
        return self.get_account(a.org_id, a.id)

    def get_account(self, org_id: str, account_id: str) -> PaperAccount | None:
        r = self._conn.execute("SELECT * FROM paper_accounts WHERE org_id=? AND id=?", (org_id, account_id)).fetchone()
        return self._acct(r) if r else None

    def account_halt_reason(self, org_id: str, account_id: str) -> str:
        r = self._conn.execute("SELECT halt_reason FROM paper_accounts WHERE org_id=? AND id=?", (org_id, account_id)).fetchone()
        return r["halt_reason"] if r else ""

    def list_accounts(self, org_id: str, *, limit: int = 200) -> list[PaperAccount]:
        rows = self._conn.execute("SELECT * FROM paper_accounts WHERE org_id=? ORDER BY created_at DESC LIMIT ?",
                                  (org_id, int(limit))).fetchall()
        return [self._acct(r) for r in rows]

    def update_account_status(self, org_id, account_id, *, expected_version, status: AccountStatus,
                              halt_reason: str = "") -> tuple[str, PaperAccount | None]:
        with self._lock, self._conn:
            cur = self.get_account(org_id, account_id)
            if not cur:
                return ("not_found", None)
            if cur.version != int(expected_version):
                return ("conflict", cur)
            cur.status = status
            cur.version += 1
            self._write_account(self._conn, cur, halt_reason=halt_reason)
        return ("ok", self.get_account(org_id, account_id))

    # ── positions ─────────────────────────────────────────────────────────────
    def get_position(self, org_id, account_id, symbol) -> PaperPosition | None:
        r = self._conn.execute("SELECT * FROM paper_positions WHERE org_id=? AND account_id=? AND symbol=?",
                               (org_id, account_id, symbol)).fetchone()
        return self._pos(r) if r else None

    def list_positions(self, org_id, account_id) -> list[PaperPosition]:
        rows = self._conn.execute("SELECT * FROM paper_positions WHERE org_id=? AND account_id=? ORDER BY symbol",
                                  (org_id, account_id)).fetchall()
        return [self._pos(r) for r in rows]

    # ── intents ───────────────────────────────────────────────────────────────
    def create_intent(self, *, intent_id, org_id, workspace_id, account_id, payload: dict, state: str,
                      correlation_id, idempotency_key, approval_id="", strategy_ref="", thesis_ref="",
                      market_data_ref="", proposed_by="", reason="") -> dict:
        ts = self._now()
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO paper_intents (intent_id,org_id,workspace_id,account_id,payload_json,guardian_json,state,"
                "reason,correlation_id,idempotency_key,approval_id,strategy_ref,thesis_ref,market_data_ref,proposed_by,"
                "version,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,?)",
                (intent_id, org_id, workspace_id, account_id, _dumps(payload), "{}", state, reason, correlation_id,
                 idempotency_key, approval_id, strategy_ref, thesis_ref, market_data_ref, proposed_by, ts, ts))
        return self.get_intent(org_id, intent_id)

    def get_intent(self, org_id, intent_id) -> dict | None:
        r = self._conn.execute("SELECT * FROM paper_intents WHERE org_id=? AND intent_id=?", (org_id, intent_id)).fetchone()
        if not r:
            return None
        d = dict(r)
        d["payload"] = json.loads(d.pop("payload_json") or "{}")
        d["guardian"] = json.loads(d.pop("guardian_json") or "{}")
        return d

    def list_intents(self, org_id, *, account_id=None, limit=200) -> list[dict]:
        if account_id:
            rows = self._conn.execute("SELECT intent_id,account_id,state,version,created_at FROM paper_intents"
                                      " WHERE org_id=? AND account_id=? ORDER BY created_at DESC LIMIT ?",
                                      (org_id, account_id, int(limit))).fetchall()
        else:
            rows = self._conn.execute("SELECT intent_id,account_id,state,version,created_at FROM paper_intents"
                                      " WHERE org_id=? ORDER BY created_at DESC LIMIT ?", (org_id, int(limit))).fetchall()
        return [dict(r) for r in rows]

    def update_intent(self, org_id, intent_id, *, state: str | None = None, guardian: dict | None = None,
                      reason: str | None = None, approval_id: str | None = None) -> dict | None:
        with self._lock, self._conn:
            cur = self.get_intent(org_id, intent_id)
            if not cur:
                return None
            self._conn.execute(
                "UPDATE paper_intents SET state=?, guardian_json=?, reason=?, approval_id=?, version=version+1,"
                " updated_at=? WHERE org_id=? AND intent_id=?",
                (state or cur["state"], _dumps(guardian if guardian is not None else cur["guardian"]),
                 reason if reason is not None else cur["reason"],
                 approval_id if approval_id is not None else cur["approval_id"], self._now(), org_id, intent_id))
        return self.get_intent(org_id, intent_id)

    # ── orders / fills reads ────────────────────────────────────────────────────
    def get_order(self, org_id, order_id) -> PaperOrder | None:
        r = self._conn.execute("SELECT * FROM paper_orders WHERE org_id=? AND id=?", (org_id, order_id)).fetchone()
        return self._order(r) if r else None

    def get_order_by_idempotency(self, org_id, key) -> PaperOrder | None:
        if not key:
            return None
        r = self._conn.execute("SELECT * FROM paper_orders WHERE org_id=? AND idempotency_key=?", (org_id, key)).fetchone()
        return self._order(r) if r else None

    def list_orders(self, org_id, *, account_id=None, limit=200, offset=0) -> list[PaperOrder]:
        if account_id:
            rows = self._conn.execute("SELECT * FROM paper_orders WHERE org_id=? AND paper_account_id=?"
                                      " ORDER BY submitted_at DESC LIMIT ? OFFSET ?",
                                      (org_id, account_id, int(limit), int(offset))).fetchall()
        else:
            rows = self._conn.execute("SELECT * FROM paper_orders WHERE org_id=? ORDER BY submitted_at DESC LIMIT ? OFFSET ?",
                                      (org_id, int(limit), int(offset))).fetchall()
        return [self._order(r) for r in rows]

    def list_fills(self, org_id, order_id, *, limit=1000, offset=0) -> list[dict]:
        rows = self._conn.execute("SELECT * FROM paper_fills WHERE org_id=? AND paper_order_id=? ORDER BY seq LIMIT ? OFFSET ?",
                                  (org_id, order_id, int(limit), int(offset))).fetchall()
        return [dict(r) for r in rows]

    def list_ledger(self, org_id, account_id, *, limit=500, offset=0) -> list[dict]:
        rows = self._conn.execute("SELECT kind,amount,balance_after,reserved_after,ref,note,ts FROM paper_ledger"
                                  " WHERE org_id=? AND account_id=? ORDER BY id LIMIT ? OFFSET ?",
                                  (org_id, account_id, int(limit), int(offset))).fetchall()
        return [dict(r) for r in rows]

    def list_transitions(self, org_id, order_id) -> list[dict]:
        rows = self._conn.execute("SELECT from_state,to_state,reason,correlation_id,ts FROM paper_transitions"
                                  " WHERE org_id=? AND paper_order_id=? ORDER BY id", (org_id, order_id)).fetchall()
        return [dict(r) for r in rows]

    def event_processed(self, order_id, event_hash) -> bool:
        r = self._conn.execute("SELECT 1 FROM paper_processed_events WHERE paper_order_id=? AND event_hash=?",
                               (order_id, event_hash)).fetchone()
        return r is not None

    # ── idempotency ─────────────────────────────────────────────────────────────
    def idem_lookup(self, org_id, scope, key, payload_hash) -> dict | None:
        r = self._conn.execute("SELECT payload_hash,result_json FROM paper_idempotency WHERE org_id=? AND scope=? AND key=?",
                               (org_id, scope, key)).fetchone()
        if not r:
            return None
        if r["payload_hash"] != payload_hash:
            raise IdempotencyConflict(f"idempotency key {key} reused with different payload")
        return json.loads(r["result_json"])

    # ── atomic submission ───────────────────────────────────────────────────────
    def persist_submit(self, *, account: PaperAccount, position: PaperPosition | None, order: PaperOrder,
                       intent_state: str, guardian: dict, transition: tuple[str, str, str],
                       ledger: tuple[str, Decimal] | None, idem_scope: str, idem_key: str, idem_payload_hash: str,
                       idem_result: dict, consume_approval: Callable[[sqlite3.Cursor], bool] | None) -> dict:
        """One atomic transaction: consume approval, write order + reservation +
        intent state + transition + ledger + idempotency record. Rolls back on any error."""
        with self._lock, self._conn:
            cur = self._conn.cursor()
            if consume_approval is not None and not consume_approval(cur):
                raise ValueError("approval not consumable (missing/expired/used/foreign)")
            self._write_account(cur, account)
            if position is not None:
                self._write_position(cur, position, order.org_id)
            self._write_order(cur, order)
            cur.execute("UPDATE paper_intents SET state=?, guardian_json=?, version=version+1, updated_at=?"
                        " WHERE org_id=? AND intent_id=?",
                        (intent_state, _dumps(guardian), self._now(), order.org_id, order.order_intent_id))
            frm, to, reason = transition
            self._write_transition(cur, order.org_id, order.id, frm, to, reason, order.correlation_id)
            if ledger is not None:
                self._write_ledger(cur, order.org_id, account.id, ledger[0], ledger[1], account.current_cash,
                                   account.reserved_cash, order.id, "reservation")
            cur.execute("INSERT INTO paper_idempotency (org_id,scope,key,payload_hash,result_json,created_at)"
                        " VALUES (?,?,?,?,?,?)",
                        (order.org_id, idem_scope, idem_key, idem_payload_hash, _dumps(idem_result), self._now()))
        return idem_result

    # ── atomic fill ─────────────────────────────────────────────────────────────
    def persist_fill(self, *, account: PaperAccount, position: PaperPosition, order: PaperOrder, fill: PaperFill,
                     transition: tuple[str, str, str], ledger_entries: list[tuple[str, Decimal, str]],
                     event_hash: str) -> bool:
        """Idempotent atomic fill. Returns False (no-op) if this order already
        processed this event. Writes fill + order + position + cash + transition + ledger."""
        with self._lock, self._conn:
            if self.event_processed(order.id, event_hash):
                return False
            cur = self._conn.cursor()
            cur.execute("INSERT INTO paper_processed_events (org_id,paper_order_id,event_hash,ts) VALUES (?,?,?,?)",
                        (order.org_id, order.id, event_hash, self._now()))
            seq = self._conn.execute("SELECT COUNT(*) c FROM paper_fills WHERE paper_order_id=?", (order.id,)).fetchone()["c"]
            fill.seq = seq
            cur.execute(
                "INSERT INTO paper_fills (id,org_id,paper_order_id,event_ts,quantity,price,gross_amount,fee,slippage,"
                "side,liquidity_ref,market_data_ref,fee_model_version,slippage_model_version,result_hash,seq,created_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (fill.id, order.org_id, order.id, fill.event_ts, str(fill.quantity), str(fill.price),
                 str(fill.gross_amount), str(fill.fee), str(fill.slippage), fill.side.value, fill.liquidity_ref,
                 fill.market_data_ref, fill.fee_model_version, fill.slippage_model_version, fill.result_hash, seq,
                 self._now()))
            self._write_account(cur, account)
            self._write_position(cur, position, order.org_id)
            self._write_order(cur, order)
            frm, to, reason = transition
            self._write_transition(cur, order.org_id, order.id, frm, to, reason, order.correlation_id)
            for kind, amount, note in ledger_entries:
                self._write_ledger(cur, order.org_id, account.id, kind, amount, account.current_cash,
                                   account.reserved_cash, order.id, note)
        return True

    # ── atomic cancel ───────────────────────────────────────────────────────────
    def persist_cancel(self, *, account: PaperAccount, position: PaperPosition | None, order: PaperOrder,
                       transition: tuple[str, str, str], ledger: tuple[str, Decimal] | None,
                       idem_scope: str, idem_key: str, idem_payload_hash: str, idem_result: dict) -> dict:
        with self._lock, self._conn:
            cur = self._conn.cursor()
            self._write_account(cur, account)
            if position is not None:
                self._write_position(cur, position, order.org_id)
            self._write_order(cur, order)
            frm, to, reason = transition
            self._write_transition(cur, order.org_id, order.id, frm, to, reason, order.correlation_id)
            if ledger is not None:
                self._write_ledger(cur, order.org_id, account.id, ledger[0], ledger[1], account.current_cash,
                                   account.reserved_cash, order.id, "release")
            if idem_key:
                cur.execute("INSERT OR REPLACE INTO paper_idempotency (org_id,scope,key,payload_hash,result_json,created_at)"
                            " VALUES (?,?,?,?,?,?)",
                            (order.org_id, idem_scope, idem_key, idem_payload_hash, _dumps(idem_result), self._now()))
        return idem_result
