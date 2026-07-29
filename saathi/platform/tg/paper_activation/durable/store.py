"""M200–M202 — Thread-safe SQLite durable store for paper governance.

Single-host multi-process safe via SQLite WAL + BEGIN IMMEDIATE transactions.
PAPER ONLY.
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import threading
import time
from decimal import Decimal
from pathlib import Path
from typing import Any

from saathi.platform.tg.paper_activation.durable.events import PaperEvent, fingerprint
from saathi.platform.tg.paper_activation.durable.schema import (
    SCHEMA_SQL,
    SCHEMA_VERSION,
    ENGINE_VERSION,
)


class DurableStoreError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class VersionConflict(DurableStoreError):
    def __init__(self, message: str = "version conflict"):
        super().__init__("VERSION_CONFLICT", message)


class IdempotencyConflict(DurableStoreError):
    def __init__(self, message: str = "idempotency conflict"):
        super().__init__("IDEMPOTENCY_CONFLICT", message)


def _dumps(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, default=str)


def _loads(s: str | None, default: Any = None) -> Any:
    if not s:
        return default if default is not None else {}
    return json.loads(s)


class DurablePaperStore:
    """Durable multi-process paper governance store."""

    def __init__(self, db_path: str | Path | None = None, *, min_free_mb: int = 128):
        env = os.environ.get("SAATHI_PAPER_GOV_DB") or ""
        default = Path(__file__).resolve().parents[5] / "data" / "platform" / "paper_gov.db"
        # parents: durable -> paper_activation -> tg -> platform -> saathi -> repo
        # wait: durable is 5 levels from repo? 
        # __file__ = .../saathi/platform/tg/paper_activation/durable/store.py
        # parents[0]=durable, [1]=paper_activation, [2]=tg, [3]=platform, [4]=saathi, [5]=repo
        self.db_path = Path(db_path) if db_path else (Path(env) if env else default)
        self.min_free_mb = min_free_mb
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False, timeout=30.0)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=15000")
        self.migrate()
        self._event_seq = self._load_max_seq()

    def _load_max_seq(self) -> int:
        with self._lock:
            row = self._conn.execute("SELECT COALESCE(MAX(seq), 0) AS m FROM pg_events").fetchone()
            return int(row["m"] if row else 0)

    def migrate(self) -> dict[str, Any]:
        pre = self.disk_preflight()
        if not pre.get("ok"):
            raise DurableStoreError("INSUFFICIENT_DISK", str(pre))
        with self._lock:
            self._conn.executescript(SCHEMA_SQL)
            now = time.time()
            self._conn.execute(
                "INSERT INTO pg_meta(key, value, updated_at) VALUES(?,?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                ("schema_version", SCHEMA_VERSION, now),
            )
            self._conn.execute(
                "INSERT INTO pg_meta(key, value, updated_at) VALUES(?,?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                ("engine_version", ENGINE_VERSION, now),
            )
            self._conn.execute(
                "INSERT INTO pg_meta(key, value, updated_at) VALUES(?,?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                ("readiness", "READY", now),
            )
            self._conn.commit()
        return {
            "schema_version": SCHEMA_VERSION,
            "engine_version": ENGINE_VERSION,
            "status": "MIGRATED",
            "db_path": str(self.db_path),
            "paper_only": True,
        }

    def disk_preflight(self) -> dict[str, Any]:
        try:
            usage = shutil.disk_usage(str(self.db_path.parent if self.db_path.parent.exists() else "."))
            free_mb = usage.free // (1024 * 1024)
            return {"ok": free_mb >= self.min_free_mb, "free_mb": free_mb, "min_free_mb": self.min_free_mb}
        except OSError as e:
            return {"ok": False, "error": str(e)}

    def health(self) -> dict[str, Any]:
        try:
            with self._lock:
                row = self._conn.execute(
                    "SELECT value FROM pg_meta WHERE key='schema_version'"
                ).fetchone()
                n_events = self._conn.execute("SELECT COUNT(*) AS c FROM pg_events").fetchone()["c"]
                n_ports = self._conn.execute("SELECT COUNT(*) AS c FROM pg_portfolios").fetchone()["c"]
            return {
                "status": "HEALTHY",
                "schema_version": row["value"] if row else None,
                "engine_version": ENGINE_VERSION,
                "db_path": str(self.db_path),
                "event_count": n_events,
                "portfolio_count": n_ports,
                "readiness": "READY",
                "disk": self.disk_preflight(),
                "paper_only": True,
                "live_authorized": False,
            }
        except sqlite3.Error as e:
            return {
                "status": "UNHEALTHY",
                "error": str(e),
                "readiness": "READ_ONLY_RECOVERY",
                "paper_only": True,
            }

    # ── transactions ─────────────────────────────────────────────────────────
    def begin_immediate(self):
        self._conn.execute("BEGIN IMMEDIATE")

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def execute(self, sql: str, params: tuple | list = ()):
        return self._conn.execute(sql, params)

    def with_tx(self, fn):
        """Run fn(conn) under BEGIN IMMEDIATE + lock. Returns fn result."""
        with self._lock:
            try:
                self.begin_immediate()
                result = fn(self)
                self.commit()
                return result
            except Exception:
                try:
                    self.rollback()
                except sqlite3.Error:
                    pass
                raise

    # ── events ───────────────────────────────────────────────────────────────
    def append_event(self, event: PaperEvent, *, allow_dup_idem: bool = False) -> PaperEvent:
        def _do(store: DurablePaperStore):
            if event.idempotency_key:
                existing = store.execute(
                    "SELECT event_id FROM pg_events WHERE idempotency_key=?",
                    (event.idempotency_key,),
                ).fetchone()
                if existing:
                    if allow_dup_idem:
                        row = store.execute(
                            "SELECT * FROM pg_events WHERE event_id=?", (existing["event_id"],)
                        ).fetchone()
                        return store._row_to_event(row)
                    raise IdempotencyConflict(f"event idempotency key exists: {event.idempotency_key}")
            store._event_seq += 1
            event.seq = store._event_seq
            row = event.to_row()
            store.execute(
                """INSERT INTO pg_events(
                    event_id, event_type, schema_version, aggregate_type, aggregate_id,
                    expected_version, resulting_version, ts, actor_type, actor_id,
                    correlation_id, causation_id, idempotency_key, payload_json,
                    payload_fingerprint, previous_event_id, audit_json, seq
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    row["event_id"], row["event_type"], row["schema_version"],
                    row["aggregate_type"], row["aggregate_id"],
                    row["expected_version"], row["resulting_version"], row["ts"],
                    row["actor_type"], row["actor_id"], row["correlation_id"],
                    row["causation_id"], row["idempotency_key"], row["payload_json"],
                    row["payload_fingerprint"], row["previous_event_id"],
                    row["audit_json"], row["seq"],
                ),
            )
            return event

        return self.with_tx(_do)

    def list_events(
        self,
        *,
        aggregate_type: str = "",
        aggregate_id: str = "",
        after_seq: int = 0,
        limit: int = 500,
    ) -> list[PaperEvent]:
        with self._lock:
            sql = "SELECT * FROM pg_events WHERE seq > ?"
            params: list[Any] = [after_seq]
            if aggregate_type:
                sql += " AND aggregate_type=?"
                params.append(aggregate_type)
            if aggregate_id:
                sql += " AND aggregate_id=?"
                params.append(aggregate_id)
            sql += " ORDER BY seq ASC LIMIT ?"
            params.append(limit)
            rows = self.execute(sql, params).fetchall()
            return [self._row_to_event(r) for r in rows]

    def _row_to_event(self, r: sqlite3.Row) -> PaperEvent:
        return PaperEvent(
            event_id=r["event_id"],
            event_type=r["event_type"],
            schema_version=r["schema_version"],
            aggregate_type=r["aggregate_type"],
            aggregate_id=r["aggregate_id"],
            expected_version=r["expected_version"],
            resulting_version=r["resulting_version"],
            ts=r["ts"],
            actor_type=r["actor_type"],
            actor_id=r["actor_id"],
            correlation_id=r["correlation_id"],
            causation_id=r["causation_id"],
            idempotency_key=r["idempotency_key"] or "",
            payload=_loads(r["payload_json"], {}),
            payload_fingerprint=r["payload_fingerprint"],
            previous_event_id=r["previous_event_id"] or "",
            audit=_loads(r["audit_json"], {}),
            seq=r["seq"],
        )

    # ── idempotency ──────────────────────────────────────────────────────────
    def get_idempotent(self, scope: str, key: str) -> dict[str, Any] | None:
        with self._lock:
            row = self.execute(
                "SELECT payload_hash, result_json FROM pg_idempotency WHERE scope=? AND key=?",
                (scope, key),
            ).fetchone()
            if not row:
                return None
            return {"payload_hash": row["payload_hash"], "result": _loads(row["result_json"])}

    def put_idempotent(self, scope: str, key: str, payload_hash: str, result: dict[str, Any]) -> None:
        def _do(store: DurablePaperStore):
            existing = store.execute(
                "SELECT payload_hash FROM pg_idempotency WHERE scope=? AND key=?",
                (scope, key),
            ).fetchone()
            if existing:
                if existing["payload_hash"] != payload_hash:
                    raise IdempotencyConflict("same key different payload")
                return
            store.execute(
                "INSERT INTO pg_idempotency(scope, key, payload_hash, result_json, created_at) VALUES(?,?,?,?,?)",
                (scope, key, payload_hash, _dumps(result), time.time()),
            )
        self.with_tx(_do)

    def effect_seen(self, effect_key: str) -> bool:
        with self._lock:
            row = self.execute(
                "SELECT 1 FROM pg_processed_effects WHERE effect_key=?", (effect_key,)
            ).fetchone()
            return bool(row)

    def mark_effect(self, effect_key: str, *, order_id: str = "", fill_ref: str = "") -> bool:
        """Return True if newly marked, False if already present (duplicate)."""
        def _do(store: DurablePaperStore):
            try:
                store.execute(
                    "INSERT INTO pg_processed_effects(effect_key, order_id, fill_ref, ts) VALUES(?,?,?,?)",
                    (effect_key, order_id, fill_ref, time.time()),
                )
                return True
            except sqlite3.IntegrityError:
                return False
        return self.with_tx(_do)

    # ── portfolios ───────────────────────────────────────────────────────────
    def save_portfolio(self, p: dict[str, Any], *, expected_version: int | None = None) -> dict[str, Any]:
        def _do(store: DurablePaperStore):
            existing = store.execute(
                "SELECT version FROM pg_portfolios WHERE id=?", (p["id"],)
            ).fetchone()
            now = time.time()
            if existing:
                ver = int(existing["version"])
                if expected_version is not None and ver != expected_version:
                    raise VersionConflict(f"portfolio version {ver} != {expected_version}")
                new_ver = ver + 1
                store.execute(
                    """UPDATE pg_portfolios SET
                        name=?, status=?, cash=?, reserved_cash=?, realized_pnl=?,
                        fees_paid=?, slippage_paid=?, peak_equity=?, day_start_equity=?,
                        week_start_equity=?, month_start_equity=?, halt_reason=?, halt_detail=?,
                        risk_limits_json=?, marks_json=?, version=?, updated_at=?
                    WHERE id=? AND version=?""",
                    (
                        p["name"], p["status"], p["cash"], p.get("reserved_cash", "0"),
                        p.get("realized_pnl", "0"), p.get("fees_paid", "0"), p.get("slippage_paid", "0"),
                        p.get("peak_equity", p["cash"]), p.get("day_start_equity", p["cash"]),
                        p.get("week_start_equity", p["cash"]), p.get("month_start_equity", p["cash"]),
                        p.get("halt_reason", "NONE"), p.get("halt_detail", ""),
                        _dumps(p.get("risk_limits", {})), _dumps(p.get("marks", {})),
                        new_ver, now, p["id"], ver,
                    ),
                )
                if store._conn.total_changes == 0:
                    raise VersionConflict("portfolio update race")
                p["version"] = new_ver
            else:
                p["version"] = 1
                store.execute(
                    """INSERT INTO pg_portfolios(
                        id, org_id, workspace_id, name, status, base_currency,
                        starting_cash, cash, reserved_cash, realized_pnl, fees_paid, slippage_paid,
                        peak_equity, day_start_equity, week_start_equity, month_start_equity,
                        halt_reason, halt_detail, risk_limits_json, marks_json, version, created_at, updated_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        p["id"], p.get("org_id", "local"), p.get("workspace_id", "local"),
                        p["name"], p["status"], p.get("base_currency", "USD"),
                        p["starting_cash"], p["cash"], p.get("reserved_cash", "0"),
                        p.get("realized_pnl", "0"), p.get("fees_paid", "0"), p.get("slippage_paid", "0"),
                        p.get("peak_equity", p["cash"]), p.get("day_start_equity", p["cash"]),
                        p.get("week_start_equity", p["cash"]), p.get("month_start_equity", p["cash"]),
                        p.get("halt_reason", "NONE"), p.get("halt_detail", ""),
                        _dumps(p.get("risk_limits", {})), _dumps(p.get("marks", {})),
                        1, p.get("created_at", now), now,
                    ),
                )
            p["updated_at"] = now
            return p
        return self.with_tx(_do)

    def get_portfolio(self, portfolio_id: str) -> dict[str, Any] | None:
        with self._lock:
            r = self.execute("SELECT * FROM pg_portfolios WHERE id=?", (portfolio_id,)).fetchone()
            if not r:
                return None
            return self._portfolio_row(r)

    def list_portfolios(self, *, org_id: str = "", workspace_id: str = "") -> list[dict[str, Any]]:
        with self._lock:
            sql = "SELECT * FROM pg_portfolios WHERE 1=1"
            params: list[Any] = []
            if org_id:
                sql += " AND org_id=?"
                params.append(org_id)
            if workspace_id:
                sql += " AND workspace_id=?"
                params.append(workspace_id)
            sql += " ORDER BY created_at DESC"
            return [self._portfolio_row(r) for r in self.execute(sql, params).fetchall()]

    def _portfolio_row(self, r: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": r["id"], "org_id": r["org_id"], "workspace_id": r["workspace_id"],
            "name": r["name"], "status": r["status"], "base_currency": r["base_currency"],
            "starting_cash": r["starting_cash"], "cash": r["cash"],
            "reserved_cash": r["reserved_cash"], "realized_pnl": r["realized_pnl"],
            "fees_paid": r["fees_paid"], "slippage_paid": r["slippage_paid"],
            "peak_equity": r["peak_equity"], "day_start_equity": r["day_start_equity"],
            "week_start_equity": r["week_start_equity"], "month_start_equity": r["month_start_equity"],
            "halt_reason": r["halt_reason"], "halt_detail": r["halt_detail"],
            "risk_limits": _loads(r["risk_limits_json"], {}),
            "marks": _loads(r["marks_json"], {}),
            "version": r["version"], "created_at": r["created_at"], "updated_at": r["updated_at"],
            "paper_only": True,
        }

    def save_position(self, portfolio_id: str, pos: dict[str, Any]) -> None:
        def _do(store: DurablePaperStore):
            store.execute(
                """INSERT INTO pg_positions(
                    portfolio_id, symbol, quantity, avg_price, realized_pnl, fees,
                    strategy_slug, lots_json, history_json, version
                ) VALUES (?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(portfolio_id, symbol) DO UPDATE SET
                    quantity=excluded.quantity, avg_price=excluded.avg_price,
                    realized_pnl=excluded.realized_pnl, fees=excluded.fees,
                    strategy_slug=excluded.strategy_slug, lots_json=excluded.lots_json,
                    history_json=excluded.history_json, version=pg_positions.version+1
                """,
                (
                    portfolio_id, pos["symbol"], str(pos["quantity"]), str(pos["avg_price"]),
                    str(pos.get("realized_pnl", 0)), str(pos.get("fees", 0)),
                    pos.get("strategy_slug", ""), _dumps(pos.get("lots", [])),
                    _dumps(pos.get("history", [])), 1,
                ),
            )
        self.with_tx(_do)

    def list_positions(self, portfolio_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self.execute(
                "SELECT * FROM pg_positions WHERE portfolio_id=?", (portfolio_id,)
            ).fetchall()
            out = []
            for r in rows:
                out.append({
                    "symbol": r["symbol"], "quantity": r["quantity"], "avg_price": r["avg_price"],
                    "realized_pnl": r["realized_pnl"], "fees": r["fees"],
                    "strategy_slug": r["strategy_slug"],
                    "lots": _loads(r["lots_json"], []),
                    "history": _loads(r["history_json"], []),
                    "version": r["version"],
                })
            return out

    # ── orders ───────────────────────────────────────────────────────────────
    def save_order(self, o: dict[str, Any], *, expected_version: int | None = None) -> dict[str, Any]:
        def _do(store: DurablePaperStore):
            existing = store.execute("SELECT version FROM pg_orders WHERE id=?", (o["id"],)).fetchone()
            now = time.time()
            if existing:
                ver = int(existing["version"])
                if expected_version is not None and ver != expected_version:
                    raise VersionConflict("order version conflict")
                new_ver = ver + 1
                store.execute(
                    """UPDATE pg_orders SET status=?, filled_qty=?, reject_reason=?,
                        avg_fill_price=?, fees=?, slippage=?, fills_json=?, version=?, updated_at=?
                    WHERE id=? AND version=?""",
                    (
                        o["status"], o.get("filled_qty", "0"), o.get("reject_reason", ""),
                        o.get("avg_fill_price", "0"), o.get("fees", "0"), o.get("slippage", "0"),
                        _dumps(o.get("fills", [])), new_ver, now, o["id"], ver,
                    ),
                )
                o["version"] = new_ver
            else:
                o["version"] = 1
                try:
                    store.execute(
                        """INSERT INTO pg_orders(
                            id, portfolio_id, strategy_slug, symbol, side, order_type, tif,
                            quantity, filled_qty, limit_price, stop_price, status, reject_reason,
                            avg_fill_price, fees, slippage, fills_json, notes, correlation_id,
                            idempotency_key, sim_inputs_json, version, created_at, updated_at
                        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (
                            o["id"], o["portfolio_id"], o.get("strategy_slug", ""), o["symbol"],
                            o["side"], o["order_type"], o.get("tif", "DAY"), o["quantity"],
                            o.get("filled_qty", "0"), o.get("limit_price"), o.get("stop_price"),
                            o["status"], o.get("reject_reason", ""), o.get("avg_fill_price", "0"),
                            o.get("fees", "0"), o.get("slippage", "0"), _dumps(o.get("fills", [])),
                            o.get("notes", ""), o.get("correlation_id", ""),
                            o.get("idempotency_key", ""), _dumps(o.get("sim_inputs", {})),
                            1, o.get("created_at", now), now,
                        ),
                    )
                except sqlite3.IntegrityError as e:
                    if "idx_pg_ord_idem" in str(e) or "UNIQUE" in str(e):
                        raise IdempotencyConflict("duplicate order idempotency key") from e
                    raise
            return o
        return self.with_tx(_do)

    def get_order(self, order_id: str) -> dict[str, Any] | None:
        with self._lock:
            r = self.execute("SELECT * FROM pg_orders WHERE id=?", (order_id,)).fetchone()
            return self._order_row(r) if r else None

    def list_orders(self, portfolio_id: str, *, status: str = "") -> list[dict[str, Any]]:
        with self._lock:
            if status:
                rows = self.execute(
                    "SELECT * FROM pg_orders WHERE portfolio_id=? AND status=? ORDER BY created_at",
                    (portfolio_id, status),
                ).fetchall()
            else:
                rows = self.execute(
                    "SELECT * FROM pg_orders WHERE portfolio_id=? ORDER BY created_at",
                    (portfolio_id,),
                ).fetchall()
            return [self._order_row(r) for r in rows]

    def _order_row(self, r: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": r["id"], "portfolio_id": r["portfolio_id"], "strategy_slug": r["strategy_slug"],
            "symbol": r["symbol"], "side": r["side"], "order_type": r["order_type"], "tif": r["tif"],
            "quantity": r["quantity"], "filled_qty": r["filled_qty"],
            "limit_price": r["limit_price"], "stop_price": r["stop_price"],
            "status": r["status"], "reject_reason": r["reject_reason"],
            "avg_fill_price": r["avg_fill_price"], "fees": r["fees"], "slippage": r["slippage"],
            "fills": _loads(r["fills_json"], []), "notes": r["notes"],
            "correlation_id": r["correlation_id"], "idempotency_key": r["idempotency_key"],
            "sim_inputs": _loads(r["sim_inputs_json"], {}),
            "version": r["version"], "created_at": r["created_at"], "updated_at": r["updated_at"],
            "paper_only": True, "live_order": False,
        }

    def enqueue_order(self, order_id: str, portfolio_id: str) -> None:
        def _do(store: DurablePaperStore):
            now = time.time()
            store.execute(
                """INSERT OR IGNORE INTO pg_order_queue(
                    order_id, portfolio_id, status, attempts, next_attempt_at,
                    lease_owner, lease_until, poison, last_error, created_at, updated_at
                ) VALUES (?,?, 'PENDING', 0, 0, '', 0, 0, '', ?, ?)""",
                (order_id, portfolio_id, now, now),
            )
        self.with_tx(_do)

    def claim_queue(self, owner: str, *, lease_sec: float = 30.0, limit: float | None = None) -> dict[str, Any] | None:
        now = now if (now := time.time()) else time.time()

        def _do(store: DurablePaperStore):
            row = store.execute(
                """SELECT * FROM pg_order_queue
                   WHERE poison=0 AND status IN ('PENDING','WORKING')
                     AND (lease_until < ? OR lease_owner='' OR lease_owner=?)
                   ORDER BY created_at ASC LIMIT 1""",
                (now, owner),
            ).fetchone()
            if not row:
                return None
            until = now + lease_sec
            cur = store.execute(
                """UPDATE pg_order_queue SET status='WORKING', lease_owner=?, lease_until=?,
                    attempts=attempts+1, updated_at=?
                WHERE order_id=? AND (lease_until < ? OR lease_owner='' OR lease_owner=?)""",
                (owner, until, now, row["order_id"], now, owner),
            )
            if cur.rowcount == 0:
                return None
            return {"order_id": row["order_id"], "portfolio_id": row["portfolio_id"], "lease_until": until}

        return self.with_tx(_do)

    def complete_queue(self, order_id: str, *, poison: bool = False, error: str = "") -> None:
        def _do(store: DurablePaperStore):
            store.execute(
                """UPDATE pg_order_queue SET status=?, poison=?, last_error=?, lease_owner='', lease_until=0, updated_at=?
                WHERE order_id=?""",
                ("POISON" if poison else "DONE", 1 if poison else 0, error, time.time(), order_id),
            )
        self.with_tx(_do)

    # ── approvals / activations ──────────────────────────────────────────────
    def save_approval(self, a: dict[str, Any]) -> dict[str, Any]:
        def _do(store: DurablePaperStore):
            existing = store.execute("SELECT version, status FROM pg_approvals WHERE id=?", (a["id"],)).fetchone()
            now = time.time()
            if existing:
                ver = int(existing["version"])
                new_ver = ver + 1
                store.execute(
                    """UPDATE pg_approvals SET status=?, decided_at=?, consumed_at=?, notes=?,
                        rejection_reason=?, operator_identity=?, version=?, immutable=?
                    WHERE id=? AND version=?""",
                    (
                        a["status"], a.get("decided_at"), a.get("consumed_at"), a.get("notes", ""),
                        a.get("rejection_reason", ""), a.get("operator_identity", ""),
                        new_ver, 1 if a.get("immutable") else 0, a["id"], ver,
                    ),
                )
                if store._conn.total_changes == 0:
                    raise VersionConflict("approval update race")
                a["version"] = new_ver
            else:
                store.execute(
                    """INSERT INTO pg_approvals(
                        id, org_id, workspace_id, strategy_slug, strategy_version, dataset_id,
                        dataset_fingerprint, qualification_fingerprint, status, reason,
                        operator_id, operator_identity, created_at, decided_at, expires_at,
                        single_use, consumed_at, notes, evidence_json, rejection_reason, version, immutable
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        a["id"], a.get("org_id", "local"), a.get("workspace_id", "local"),
                        a["strategy_slug"], a.get("strategy_version", "1.0.0"), a.get("dataset_id", ""),
                        a.get("dataset_fingerprint", ""), a.get("qualification_fingerprint", ""),
                        a["status"], a["reason"], a.get("operator_id", ""), a.get("operator_identity", ""),
                        a.get("created_at", now), a.get("decided_at"), a.get("expires_at"),
                        1 if a.get("single_use", True) else 0, a.get("consumed_at"),
                        a.get("notes", ""), _dumps(a.get("evidence", {})), a.get("rejection_reason", ""),
                        1, 0,
                    ),
                )
                a["version"] = 1
            return a
        return self.with_tx(_do)

    def consume_approval_once(self, approval_id: str, *, actor: str) -> dict[str, Any]:
        """Atomic single-use consume. Fails if already consumed."""
        def _do(store: DurablePaperStore):
            row = store.execute(
                "SELECT * FROM pg_approvals WHERE id=?", (approval_id,)
            ).fetchone()
            if not row:
                raise DurableStoreError("NOT_FOUND", "approval not found")
            if row["status"] != "APPROVED":
                raise DurableStoreError("NOT_APPROVED", f"status={row['status']}")
            if row["status"] == "CONSUMED" or row["consumed_at"]:
                raise DurableStoreError("ALREADY_CONSUMED", "approval already consumed")
            now = time.time()
            cur = store.execute(
                """UPDATE pg_approvals SET status='CONSUMED', consumed_at=?, version=version+1, immutable=1
                WHERE id=? AND status='APPROVED' AND consumed_at IS NULL""",
                (now, approval_id),
            )
            if cur.rowcount != 1:
                raise DurableStoreError("ALREADY_CONSUMED", "concurrent consume")
            return {"id": approval_id, "status": "CONSUMED", "consumed_at": now, "actor": actor}
        return self.with_tx(_do)

    def get_approval(self, approval_id: str) -> dict[str, Any] | None:
        with self._lock:
            r = self.execute("SELECT * FROM pg_approvals WHERE id=?", (approval_id,)).fetchone()
            if not r:
                return None
            return {
                "id": r["id"], "org_id": r["org_id"], "workspace_id": r["workspace_id"],
                "strategy_slug": r["strategy_slug"], "strategy_version": r["strategy_version"],
                "dataset_id": r["dataset_id"], "dataset_fingerprint": r["dataset_fingerprint"],
                "qualification_fingerprint": r["qualification_fingerprint"],
                "status": r["status"], "reason": r["reason"],
                "operator_id": r["operator_id"], "operator_identity": r["operator_identity"],
                "created_at": r["created_at"], "decided_at": r["decided_at"],
                "expires_at": r["expires_at"], "single_use": bool(r["single_use"]),
                "consumed_at": r["consumed_at"], "notes": r["notes"],
                "evidence": _loads(r["evidence_json"], {}),
                "rejection_reason": r["rejection_reason"], "version": r["version"],
                "immutable": bool(r["immutable"]), "paper_only": True, "llm_may_approve": False,
            }

    def list_approvals(self, *, org_id: str = "", status: str = "") -> list[dict[str, Any]]:
        with self._lock:
            sql = "SELECT id FROM pg_approvals WHERE 1=1"
            params: list[Any] = []
            if org_id:
                sql += " AND org_id=?"
                params.append(org_id)
            if status:
                sql += " AND status=?"
                params.append(status)
            sql += " ORDER BY created_at DESC"
            ids = [r["id"] for r in self.execute(sql, params).fetchall()]
        return [a for aid in ids if (a := self.get_approval(aid))]

    def save_activation(self, rec: dict[str, Any]) -> dict[str, Any]:
        def _do(store: DurablePaperStore):
            now = time.time()
            store.execute(
                """INSERT INTO pg_activations(
                    id, org_id, workspace_id, strategy_slug, strategy_version, state,
                    qualification_verdict, qualification_fingerprint, dataset_id, dataset_fingerprint,
                    approval_id, portfolio_id, activated_at, halted_at, halt_reason, history_json,
                    version, created_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(org_id, workspace_id, strategy_slug) DO UPDATE SET
                    state=excluded.state, approval_id=excluded.approval_id,
                    portfolio_id=excluded.portfolio_id, activated_at=excluded.activated_at,
                    halted_at=excluded.halted_at, halt_reason=excluded.halt_reason,
                    history_json=excluded.history_json, version=pg_activations.version+1,
                    updated_at=excluded.updated_at,
                    qualification_verdict=excluded.qualification_verdict,
                    qualification_fingerprint=excluded.qualification_fingerprint
                """,
                (
                    rec["id"], rec.get("org_id", "local"), rec.get("workspace_id", "local"),
                    rec["strategy_slug"], rec.get("strategy_version", "1.0.0"), rec["state"],
                    rec.get("qualification_verdict", ""), rec.get("qualification_fingerprint", ""),
                    rec.get("dataset_id", ""), rec.get("dataset_fingerprint", ""),
                    rec.get("approval_id", ""), rec.get("portfolio_id", ""),
                    rec.get("activated_at"), rec.get("halted_at"), rec.get("halt_reason", ""),
                    _dumps(rec.get("history", [])), 1, rec.get("created_at", now), now,
                ),
            )
            return rec
        return self.with_tx(_do)

    def get_activation(self, strategy_slug: str, *, org_id: str = "local", workspace_id: str = "local") -> dict | None:
        with self._lock:
            r = self.execute(
                "SELECT * FROM pg_activations WHERE org_id=? AND workspace_id=? AND strategy_slug=?",
                (org_id, workspace_id, strategy_slug),
            ).fetchone()
            if not r:
                return None
            return {
                "id": r["id"], "org_id": r["org_id"], "workspace_id": r["workspace_id"],
                "strategy_slug": r["strategy_slug"], "strategy_version": r["strategy_version"],
                "state": r["state"], "qualification_verdict": r["qualification_verdict"],
                "qualification_fingerprint": r["qualification_fingerprint"],
                "dataset_id": r["dataset_id"], "dataset_fingerprint": r["dataset_fingerprint"],
                "approval_id": r["approval_id"], "portfolio_id": r["portfolio_id"],
                "activated_at": r["activated_at"], "halted_at": r["halted_at"],
                "halt_reason": r["halt_reason"], "history": _loads(r["history_json"], []),
                "version": r["version"], "paper_only": True, "live_authorized": False,
            }

    # ── kill switch ──────────────────────────────────────────────────────────
    def set_kill_switch(self, *, scope: str, active: bool, reason: str, activated_by: str,
                        org_id: str = "", workspace_id: str = "", scope_ref: str = "") -> dict[str, Any]:
        def _do(store: DurablePaperStore):
            kid = f"{org_id}|{workspace_id}|{scope}|{scope_ref}"
            now = time.time()
            store.execute(
                """INSERT INTO pg_kill_switch(id, scope, scope_ref, active, reason, activated_by, org_id, workspace_id, version, updated_at)
                VALUES (?,?,?,?,?,?,?,?,1,?)
                ON CONFLICT(id) DO UPDATE SET active=excluded.active, reason=excluded.reason,
                    activated_by=excluded.activated_by, version=pg_kill_switch.version+1, updated_at=excluded.updated_at
                """,
                (kid, scope, scope_ref, 1 if active else 0, reason, activated_by, org_id, workspace_id, now),
            )
            return {"id": kid, "scope": scope, "active": active, "reason": reason, "paper_only": True}
        return self.with_tx(_do)

    def kill_switch_active(self, *, org_id: str = "", workspace_id: str = "") -> bool:
        with self._lock:
            rows = self.execute("SELECT * FROM pg_kill_switch WHERE active=1").fetchall()
            for r in rows:
                if r["scope"] in ("GLOBAL", "TRADING_GUARDIAN"):
                    if r["org_id"] and org_id and r["org_id"] != org_id:
                        continue
                    if r["workspace_id"] and workspace_id and r["workspace_id"] != workspace_id:
                        continue
                    return True
            return False

    def list_kill_switches(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                {
                    "id": r["id"], "scope": r["scope"], "active": bool(r["active"]),
                    "reason": r["reason"], "activated_by": r["activated_by"],
                    "version": r["version"], "paper_only": True,
                }
                for r in self.execute("SELECT * FROM pg_kill_switch").fetchall()
            ]

    # ── journal / ledger / recon / snapshots ─────────────────────────────────
    def append_journal(self, entry: dict[str, Any]) -> None:
        def _do(store: DurablePaperStore):
            store.execute(
                """INSERT INTO pg_journal(id, portfolio_id, strategy_slug, order_id, symbol, side, reason, payload_json, org_id, workspace_id, created_at, immutable)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,1)""",
                (
                    entry["id"], entry["portfolio_id"], entry.get("strategy_slug", ""),
                    entry.get("order_id", ""), entry.get("symbol", ""), entry.get("side", ""),
                    entry.get("reason", ""), _dumps(entry), entry.get("org_id", ""),
                    entry.get("workspace_id", ""), entry.get("created_at", time.time()),
                ),
            )
        self.with_tx(_do)

    def list_journal(self, portfolio_id: str, *, limit: int = 200) -> list[dict[str, Any]]:
        with self._lock:
            rows = self.execute(
                "SELECT payload_json FROM pg_journal WHERE portfolio_id=? ORDER BY created_at DESC LIMIT ?",
                (portfolio_id, limit),
            ).fetchall()
            return [_loads(r["payload_json"], {}) for r in rows]

    def append_trade_ledger(self, portfolio_id: str, entry: dict[str, Any]) -> None:
        def _do(store: DurablePaperStore):
            store.execute(
                "INSERT INTO pg_trade_ledger(portfolio_id, entry_json, ts) VALUES (?,?,?)",
                (portfolio_id, _dumps(entry), entry.get("ts", time.time())),
            )
        self.with_tx(_do)

    def list_trade_ledger(self, portfolio_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self.execute(
                "SELECT entry_json FROM pg_trade_ledger WHERE portfolio_id=? ORDER BY id",
                (portfolio_id,),
            ).fetchall()
            return [_loads(r["entry_json"], {}) for r in rows]

    def save_reconciliation(self, rec: dict[str, Any]) -> None:
        def _do(store: DurablePaperStore):
            store.execute(
                """INSERT INTO pg_reconciliation(id, portfolio_id, verdict, findings_json, warnings_json, created_at)
                VALUES (?,?,?,?,?,?)""",
                (
                    rec["id"], rec["portfolio_id"], rec["verdict"],
                    _dumps(rec.get("findings", [])), _dumps(rec.get("warnings", [])),
                    rec.get("created_at", time.time()),
                ),
            )
        self.with_tx(_do)

    def save_snapshot(self, snap: dict[str, Any]) -> dict[str, Any]:
        def _do(store: DurablePaperStore):
            fp = fingerprint(snap.get("state", {}))
            store.execute(
                """INSERT INTO pg_snapshots(id, portfolio_id, seq_upto, state_json, fingerprint, created_at)
                VALUES (?,?,?,?,?,?)""",
                (
                    snap["id"], snap["portfolio_id"], snap.get("seq_upto", 0),
                    _dumps(snap.get("state", {})), fp, time.time(),
                ),
            )
            snap["fingerprint"] = fp
            return snap
        return self.with_tx(_do)

    def latest_snapshot(self, portfolio_id: str) -> dict[str, Any] | None:
        with self._lock:
            r = self.execute(
                "SELECT * FROM pg_snapshots WHERE portfolio_id=? ORDER BY created_at DESC LIMIT 1",
                (portfolio_id,),
            ).fetchone()
            if not r:
                return None
            return {
                "id": r["id"], "portfolio_id": r["portfolio_id"], "seq_upto": r["seq_upto"],
                "state": _loads(r["state_json"], {}), "fingerprint": r["fingerprint"],
                "created_at": r["created_at"],
            }

    # ── campaigns ────────────────────────────────────────────────────────────
    def save_campaign(self, c: dict[str, Any]) -> dict[str, Any]:
        def _do(store: DurablePaperStore):
            now = time.time()
            store.execute(
                """INSERT INTO pg_campaigns(
                    id, org_id, workspace_id, portfolio_id, strategy_slug, strategy_version,
                    dataset_fingerprint, qualification_fingerprint, approval_id, status,
                    start_date, planned_end_date, actual_end_date, initial_cash,
                    allowed_symbols_json, risk_policy_version, cost_model_version,
                    objectives_json, evaluation_criteria_json, min_duration_sec, min_trade_count,
                    operator_notes, evidence_json, version, created_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                    status=excluded.status, portfolio_id=excluded.portfolio_id,
                    approval_id=excluded.approval_id, start_date=excluded.start_date,
                    actual_end_date=excluded.actual_end_date, evidence_json=excluded.evidence_json,
                    version=pg_campaigns.version+1, updated_at=excluded.updated_at
                """,
                (
                    c["id"], c.get("org_id", "local"), c.get("workspace_id", "local"),
                    c.get("portfolio_id", ""), c["strategy_slug"], c.get("strategy_version", "1.0.0"),
                    c.get("dataset_fingerprint", ""), c.get("qualification_fingerprint", ""),
                    c.get("approval_id", ""), c.get("status", "DRAFT"),
                    c.get("start_date"), c.get("planned_end_date"), c.get("actual_end_date"),
                    c.get("initial_cash", "100000"), _dumps(c.get("allowed_symbols", [])),
                    c.get("risk_policy_version", "1.0.0"), c.get("cost_model_version", "1.0.0"),
                    _dumps(c.get("objectives", {})), _dumps(c.get("evaluation_criteria", {})),
                    c.get("min_duration_sec", 0), c.get("min_trade_count", 0),
                    c.get("operator_notes", ""), _dumps(c.get("evidence", {})),
                    1, c.get("created_at", now), now,
                ),
            )
            return c
        return self.with_tx(_do)

    def get_campaign(self, campaign_id: str) -> dict[str, Any] | None:
        with self._lock:
            r = self.execute("SELECT * FROM pg_campaigns WHERE id=?", (campaign_id,)).fetchone()
            if not r:
                return None
            return self._campaign_row(r)

    def list_campaigns(self, *, org_id: str = "", status: str = "") -> list[dict[str, Any]]:
        with self._lock:
            sql = "SELECT * FROM pg_campaigns WHERE 1=1"
            params: list[Any] = []
            if org_id:
                sql += " AND org_id=?"
                params.append(org_id)
            if status:
                sql += " AND status=?"
                params.append(status)
            return [self._campaign_row(r) for r in self.execute(sql, params).fetchall()]

    def _campaign_row(self, r: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": r["id"], "org_id": r["org_id"], "workspace_id": r["workspace_id"],
            "portfolio_id": r["portfolio_id"], "strategy_slug": r["strategy_slug"],
            "strategy_version": r["strategy_version"],
            "dataset_fingerprint": r["dataset_fingerprint"],
            "qualification_fingerprint": r["qualification_fingerprint"],
            "approval_id": r["approval_id"], "status": r["status"],
            "start_date": r["start_date"], "planned_end_date": r["planned_end_date"],
            "actual_end_date": r["actual_end_date"], "initial_cash": r["initial_cash"],
            "allowed_symbols": _loads(r["allowed_symbols_json"], []),
            "risk_policy_version": r["risk_policy_version"],
            "cost_model_version": r["cost_model_version"],
            "objectives": _loads(r["objectives_json"], {}),
            "evaluation_criteria": _loads(r["evaluation_criteria_json"], {}),
            "min_duration_sec": r["min_duration_sec"], "min_trade_count": r["min_trade_count"],
            "operator_notes": r["operator_notes"], "evidence": _loads(r["evidence_json"], {}),
            "version": r["version"], "created_at": r["created_at"], "updated_at": r["updated_at"],
            "paper_only": True, "live_authorized": False,
        }

    # ── scheduler / incidents ────────────────────────────────────────────────
    def upsert_job(self, job_id: str, *, enabled: bool = False, interval_sec: float = 86400) -> None:
        def _do(store: DurablePaperStore):
            store.execute(
                """INSERT INTO pg_scheduler(job_id, enabled, last_run_at, last_status, last_error, interval_sec, meta_json)
                VALUES (?,?,0,'','',?,'{}')
                ON CONFLICT(job_id) DO UPDATE SET enabled=excluded.enabled, interval_sec=excluded.interval_sec
                """,
                (job_id, 1 if enabled else 0, interval_sec),
            )
        self.with_tx(_do)

    def mark_job_run(self, job_id: str, *, status: str, error: str = "") -> None:
        def _do(store: DurablePaperStore):
            store.execute(
                "UPDATE pg_scheduler SET last_run_at=?, last_status=?, last_error=? WHERE job_id=?",
                (time.time(), status, error, job_id),
            )
        self.with_tx(_do)

    def list_jobs(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                {
                    "job_id": r["job_id"], "enabled": bool(r["enabled"]),
                    "last_run_at": r["last_run_at"], "last_status": r["last_status"],
                    "last_error": r["last_error"], "interval_sec": r["interval_sec"],
                }
                for r in self.execute("SELECT * FROM pg_scheduler").fetchall()
            ]

    def open_incident(self, inc: dict[str, Any]) -> dict[str, Any]:
        def _do(store: DurablePaperStore):
            now = time.time()
            store.execute(
                """INSERT INTO pg_incidents(id, severity, kind, message, portfolio_id, campaign_id, status, created_at, updated_at)
                VALUES (?,?,?,?,?,?, 'OPEN', ?, ?)""",
                (
                    inc["id"], inc.get("severity", "warning"), inc["kind"], inc["message"],
                    inc.get("portfolio_id", ""), inc.get("campaign_id", ""), now, now,
                ),
            )
            return inc
        return self.with_tx(_do)

    def list_incidents(self, *, status: str = "OPEN") -> list[dict[str, Any]]:
        with self._lock:
            rows = self.execute(
                "SELECT * FROM pg_incidents WHERE status=? ORDER BY created_at DESC", (status,)
            ).fetchall()
            return [dict(r) for r in rows]

    def close(self) -> None:
        with self._lock:
            self._conn.close()
