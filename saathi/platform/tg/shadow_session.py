"""SHADOW-TRADING-1 — durable shadow sessions over the SHADOW-1 engine.

SHADOW-1 already proves the decision chain can be observed without sending an
order, but it lives entirely in memory: kill the process and the session, the
accounting and the counterfactual record are gone. This module is the durable
operating layer around it.

SHADOW IS NOT PAPER. Paper simulates a broker. Shadow observes real public market
conditions and records what SaathiOS WOULD have done. Nothing here submits, and
there is no venue client, no broker adapter import, and no submit/execute entry
point anywhere in this module — the no-order property is structural, not a flag.

Durability follows the RESEARCH-3 idiom exactly: a versioned schema on the
canonical ``ResearchStore`` connection, so shadow records live beside the decision
journal they reference instead of in a parallel store.

The invariant that shapes the accounting: a restart must never double-count. Every
event carries a per-session monotonic sequence with a UNIQUE constraint, so
replaying the same event after a crash is a no-op rather than a second fill, a
second fee, or a second charge against cash.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any

from saathi.platform.research.store import ResearchStore

SHADOW_SESSION_SCHEMA_VERSION = 1

# Shadow may only ever run against these. A live venue account is not one of them.
class ShadowMode(str, Enum):
    REPLAY = "REPLAY"            # deterministic historical observations
    LIVE_PUBLIC = "LIVE_PUBLIC"  # real public market data, still no order


class ShadowSessionStatus(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"


class ShadowEventKind(str, Enum):
    OBSERVATION = "OBSERVATION"
    SIGNAL = "SIGNAL"
    INTENT = "INTENT"
    CONSTRUCTION = "CONSTRUCTION"
    RISK = "RISK"
    GUARDIAN = "GUARDIAN"
    HYPOTHETICAL_ORDER = "HYPOTHETICAL_ORDER"
    HYPOTHETICAL_FILL = "HYPOTHETICAL_FILL"
    BLOCKED_COUNTERFACTUAL = "BLOCKED_COUNTERFACTUAL"
    DEGRADATION = "DEGRADATION"


class StrategyHealth(str, Enum):
    NORMAL = "NORMAL"
    WATCH = "WATCH"
    DEGRADED = "DEGRADED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class ShadowError(RuntimeError):
    pass


class ShadowReconciliationError(ShadowError):
    """Raised when derived state disagrees with recorded state. Fail closed."""


class ShadowAuthorityError(ShadowError):
    """Raised if anything attempts to give a shadow object execution authority."""


_SCHEMA_V1 = """
CREATE TABLE IF NOT EXISTS shadow_sessions (
    session_id TEXT PRIMARY KEY,
    mode TEXT NOT NULL,
    market TEXT NOT NULL,
    strategy_version TEXT NOT NULL,
    policy_versions TEXT NOT NULL,
    feed_ref TEXT NOT NULL,
    benchmark TEXT,
    opening_cash TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    status TEXT NOT NULL,
    schema_version INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS shadow_events (
    session_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    kind TEXT NOT NULL,
    observed_at TEXT,
    payload TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    PRIMARY KEY (session_id, seq)
);
CREATE TABLE IF NOT EXISTS shadow_fills (
    session_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    quantity TEXT NOT NULL,
    reference_price TEXT NOT NULL,
    fill_price TEXT NOT NULL,
    fee TEXT NOT NULL,
    spread_cost TEXT NOT NULL,
    slippage_cost TEXT NOT NULL,
    PRIMARY KEY (session_id, seq)
);
CREATE TABLE IF NOT EXISTS shadow_counterfactuals (
    session_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    quantity TEXT NOT NULL,
    reference_price TEXT NOT NULL,
    blocked_by TEXT NOT NULL,
    reason_codes TEXT NOT NULL,
    forward_price TEXT,
    forward_pnl TEXT,
    PRIMARY KEY (session_id, seq)
);
CREATE INDEX IF NOT EXISTS shadow_events_session ON shadow_events(session_id, kind);
"""


def _d(value: Any) -> Decimal:
    """Decimal or refuse. Money is never parsed loosely."""
    if isinstance(value, Decimal):
        return value
    if value is None or isinstance(value, bool):
        raise ShadowError(f"not a quantity: {value!r}")
    return Decimal(str(value))


def _canonical(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def _hash(payload: dict[str, Any]) -> str:
    from hashlib import sha256
    return sha256(_canonical(payload).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ShadowPortfolioState:
    """Derived shadow portfolio. Never mixed with real, paper or operator books."""
    mode: str = "SHADOW"
    cash: Decimal = Decimal("0")
    positions: dict[str, Decimal] = field(default_factory=dict)
    cost_basis: dict[str, Decimal] = field(default_factory=dict)
    fees_paid: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")
    turnover: Decimal = Decimal("0")
    fills: int = 0

    def nav(self, price_map: dict[str, Any] | None = None) -> Decimal:
        prices = price_map or {}
        market = Decimal("0")
        for sym, qty in self.positions.items():
            px = prices.get(sym)
            if px is None:
                # An unpriced position is NOT zero. NAV is refused rather than
                # understated — the same rule the NEPSE portfolio follows.
                raise ShadowError(f"NAV unavailable: no price for {sym}")
            market += qty * _d(px)
        return self.cash + market


class ShadowSessionStore:
    """Versioned durable shadow records on a ResearchStore connection."""

    def __init__(self, *, research_store: ResearchStore | None = None, busy_timeout_ms: int = 1_000):
        self.research_store = research_store or ResearchStore()
        self.connection: sqlite3.Connection = self.research_store._conn
        self.db_path = Path(self.research_store.db_path)
        self.connection.execute(f"PRAGMA busy_timeout={max(1, int(busy_timeout_ms))}")
        self._migrate()

    def _migrate(self) -> None:
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS shadow_session_meta "
            "(singleton INTEGER PRIMARY KEY CHECK(singleton=1), schema_version INTEGER NOT NULL)"
        )
        row = self.connection.execute(
            "SELECT schema_version FROM shadow_session_meta WHERE singleton=1"
        ).fetchone()
        current = int(row[0]) if row else 0
        if current > SHADOW_SESSION_SCHEMA_VERSION:
            raise ShadowError(
                f"shadow schema {current} is newer than supported {SHADOW_SESSION_SCHEMA_VERSION}"
            )
        self.connection.executescript(_SCHEMA_V1)
        if current == 0:
            self.connection.execute(
                "INSERT INTO shadow_session_meta(singleton,schema_version) VALUES (1,?)",
                (SHADOW_SESSION_SCHEMA_VERSION,),
            )
        self.connection.commit()

    @property
    def schema_version(self) -> int:
        row = self.connection.execute(
            "SELECT schema_version FROM shadow_session_meta WHERE singleton=1"
        ).fetchone()
        return int(row[0])

    def close(self) -> None:
        self.connection.close()

    # ── sessions ────────────────────────────────────────────────────────────
    def open_session(
        self, *, mode: ShadowMode, market: str, strategy_version: str,
        policy_versions: dict[str, str], feed_ref: str, opening_cash: Any,
        started_at: str, benchmark: str | None = None, session_id: str | None = None,
    ) -> str:
        sid = session_id or f"shadow-{uuid.uuid4().hex[:16]}"
        self.connection.execute(
            "INSERT INTO shadow_sessions(session_id,mode,market,strategy_version,policy_versions,"
            "feed_ref,benchmark,opening_cash,started_at,ended_at,status,schema_version) "
            "VALUES (?,?,?,?,?,?,?,?,?,NULL,?,?)",
            (sid, ShadowMode(mode).value, market, strategy_version,
             _canonical(policy_versions), feed_ref, benchmark, str(_d(opening_cash)),
             started_at, ShadowSessionStatus.OPEN.value, SHADOW_SESSION_SCHEMA_VERSION),
        )
        self.connection.commit()
        return sid

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT session_id,mode,market,strategy_version,policy_versions,feed_ref,benchmark,"
            "opening_cash,started_at,ended_at,status FROM shadow_sessions WHERE session_id=?",
            (session_id,),
        ).fetchone()
        if not row:
            return None
        keys = ("session_id", "mode", "market", "strategy_version", "policy_versions",
                "feed_ref", "benchmark", "opening_cash", "started_at", "ended_at", "status")
        out = dict(zip(keys, row))
        out["policy_versions"] = json.loads(out["policy_versions"])
        return out

    def set_status(self, session_id: str, status: ShadowSessionStatus, *, ended_at: str | None = None) -> None:
        self.connection.execute(
            "UPDATE shadow_sessions SET status=?, ended_at=COALESCE(?, ended_at) WHERE session_id=?",
            (ShadowSessionStatus(status).value, ended_at, session_id),
        )
        self.connection.commit()

    # ── events ──────────────────────────────────────────────────────────────
    def next_seq(self, session_id: str) -> int:
        row = self.connection.execute(
            "SELECT COALESCE(MAX(seq),0) FROM shadow_events WHERE session_id=?", (session_id,)
        ).fetchone()
        return int(row[0]) + 1

    def append_event(
        self, session_id: str, seq: int, kind: ShadowEventKind,
        payload: dict[str, Any], *, observed_at: str | None = None,
    ) -> bool:
        """Append one event. Returns False if this seq already exists.

        Idempotency lives here: a restart that replays an already-recorded event
        must NOT produce a second fill, fee or cash movement. The UNIQUE key makes
        that a no-op rather than a duplicate, and a DIFFERENT payload on an
        existing seq is a hard error — that is history being rewritten.
        """
        existing = self.connection.execute(
            "SELECT content_hash FROM shadow_events WHERE session_id=? AND seq=?",
            (session_id, seq),
        ).fetchone()
        h = _hash(payload)
        if existing:
            if existing[0] != h:
                raise ShadowError(
                    f"event {session_id}#{seq} already recorded with different content"
                )
            return False
        self.connection.execute(
            "INSERT INTO shadow_events(session_id,seq,kind,observed_at,payload,content_hash) "
            "VALUES (?,?,?,?,?,?)",
            (session_id, seq, ShadowEventKind(kind).value, observed_at, _canonical(payload), h),
        )
        self.connection.commit()
        return True

    def events(self, session_id: str, kind: ShadowEventKind | None = None) -> list[dict[str, Any]]:
        sql = "SELECT seq,kind,observed_at,payload FROM shadow_events WHERE session_id=?"
        args: list[Any] = [session_id]
        if kind is not None:
            sql += " AND kind=?"
            args.append(ShadowEventKind(kind).value)
        sql += " ORDER BY seq"
        return [
            {"seq": r[0], "kind": r[1], "observed_at": r[2], "payload": json.loads(r[3])}
            for r in self.connection.execute(sql, args).fetchall()
        ]

    # ── fills ───────────────────────────────────────────────────────────────
    def record_fill(
        self, session_id: str, seq: int, *, symbol: str, side: str, quantity: Any,
        reference_price: Any, fill_price: Any, fee: Any,
        spread_cost: Any = 0, slippage_cost: Any = 0,
    ) -> bool:
        """Record a HYPOTHETICAL fill. Keyed on seq, so a replay cannot double it."""
        if self.connection.execute(
            "SELECT 1 FROM shadow_fills WHERE session_id=? AND seq=?", (session_id, seq)
        ).fetchone():
            return False
        self.connection.execute(
            "INSERT INTO shadow_fills(session_id,seq,symbol,side,quantity,reference_price,"
            "fill_price,fee,spread_cost,slippage_cost) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (session_id, seq, symbol, side.upper(), str(_d(quantity)), str(_d(reference_price)),
             str(_d(fill_price)), str(_d(fee)), str(_d(spread_cost)), str(_d(slippage_cost))),
        )
        self.connection.commit()
        return True

    def fills(self, session_id: str, *, max_seq: int | None = None) -> list[dict[str, Any]]:
        """Fills, optionally truncated at a sequence cutoff.

        `max_seq` exists for point-in-time reads: seq is this session's canonical
        ordering, so bounding it is how a caller asks "what did we know by then?"
        without needing a clock. Omitted, behaviour is unchanged.
        """
        sql = ("SELECT seq,symbol,side,quantity,reference_price,fill_price,fee,spread_cost,slippage_cost "
               "FROM shadow_fills WHERE session_id=?")
        args: list[Any] = [session_id]
        if max_seq is not None:
            sql += " AND seq<=?"
            args.append(int(max_seq))
        rows = self.connection.execute(sql + " ORDER BY seq", tuple(args)).fetchall()
        return [
            {"seq": r[0], "symbol": r[1], "side": r[2], "quantity": Decimal(r[3]),
             "reference_price": Decimal(r[4]), "fill_price": Decimal(r[5]), "fee": Decimal(r[6]),
             "spread_cost": Decimal(r[7]), "slippage_cost": Decimal(r[8])}
            for r in rows
        ]

    # ── counterfactuals ─────────────────────────────────────────────────────
    def record_blocked(
        self, session_id: str, seq: int, *, symbol: str, side: str, quantity: Any,
        reference_price: Any, blocked_by: str, reason_codes: list[str],
    ) -> bool:
        """A trade Guardian refused. Recorded so its counterfactual can be measured.

        This has ZERO execution authority: nothing reads this table to place, size
        or unblock anything. A blocked trade stays blocked forever.
        """
        if self.connection.execute(
            "SELECT 1 FROM shadow_counterfactuals WHERE session_id=? AND seq=?", (session_id, seq)
        ).fetchone():
            return False
        self.connection.execute(
            "INSERT INTO shadow_counterfactuals(session_id,seq,symbol,side,quantity,"
            "reference_price,blocked_by,reason_codes,forward_price,forward_pnl) "
            "VALUES (?,?,?,?,?,?,?,?,NULL,NULL)",
            (session_id, seq, symbol, side.upper(), str(_d(quantity)), str(_d(reference_price)),
             blocked_by, _canonical({"codes": list(reason_codes)})),
        )
        self.connection.commit()
        return True

    def observe_counterfactual(self, session_id: str, seq: int, forward_price: Any) -> dict[str, Any]:
        """Attach a later observed price to a blocked proposal and measure it."""
        row = self.connection.execute(
            "SELECT symbol,side,quantity,reference_price FROM shadow_counterfactuals "
            "WHERE session_id=? AND seq=?", (session_id, seq)
        ).fetchone()
        if not row:
            raise ShadowError(f"no blocked proposal {session_id}#{seq}")
        symbol, side, qty, ref = row[0], row[1], Decimal(row[2]), Decimal(row[3])
        fwd = _d(forward_price)
        direction = Decimal("1") if side == "BUY" else Decimal("-1")
        pnl = (fwd - ref) * qty * direction
        self.connection.execute(
            "UPDATE shadow_counterfactuals SET forward_price=?, forward_pnl=? WHERE session_id=? AND seq=?",
            (str(fwd), str(pnl), session_id, seq),
        )
        self.connection.commit()
        return {"symbol": symbol, "side": side, "quantity": qty, "reference_price": ref,
                "forward_price": fwd, "forward_pnl": pnl}

    def counterfactuals(self, session_id: str) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT seq,symbol,side,quantity,reference_price,blocked_by,reason_codes,"
            "forward_price,forward_pnl FROM shadow_counterfactuals WHERE session_id=? ORDER BY seq",
            (session_id,),
        ).fetchall()
        return [
            {"seq": r[0], "symbol": r[1], "side": r[2], "quantity": Decimal(r[3]),
             "reference_price": Decimal(r[4]), "blocked_by": r[5],
             "reason_codes": json.loads(r[6])["codes"],
             "forward_price": Decimal(r[7]) if r[7] is not None else None,
             "forward_pnl": Decimal(r[8]) if r[8] is not None else None}
            for r in rows
        ]

    # ── derived portfolio + reconciliation ──────────────────────────────────
    def derive_portfolio(self, session_id: str, *, max_seq: int | None = None) -> ShadowPortfolioState:
        """Rebuild the shadow book from its fills alone.

        Deriving rather than storing is deliberate: a stored balance can drift
        from its own history, and a restart that trusts the balance would inherit
        the drift silently.
        """
        session = self.get_session(session_id)
        if session is None:
            raise ShadowError(f"unknown shadow session {session_id}")
        cash = Decimal(session["opening_cash"])
        positions: dict[str, Decimal] = {}
        basis: dict[str, Decimal] = {}
        fees = Decimal("0")
        realized = Decimal("0")
        turnover = Decimal("0")
        n = 0
        for f in self.fills(session_id, max_seq=max_seq):
            qty, px, fee = f["quantity"], f["fill_price"], f["fee"]
            notional = qty * px
            turnover += notional
            fees += fee
            n += 1
            if f["side"] == "BUY":
                cash -= notional + fee
                prev_q = positions.get(f["symbol"], Decimal("0"))
                prev_b = basis.get(f["symbol"], Decimal("0"))
                positions[f["symbol"]] = prev_q + qty
                basis[f["symbol"]] = prev_b + notional
            else:
                held = positions.get(f["symbol"], Decimal("0"))
                if qty > held:
                    raise ShadowReconciliationError(
                        f"{session_id}#{f['seq']}: sell {qty} exceeds held {held} of {f['symbol']}"
                    )
                avg = (basis.get(f["symbol"], Decimal("0")) / held) if held else Decimal("0")
                realized += (px - avg) * qty - fee
                cash += notional - fee
                positions[f["symbol"]] = held - qty
                basis[f["symbol"]] = basis.get(f["symbol"], Decimal("0")) - avg * qty
                if positions[f["symbol"]] == 0:
                    positions.pop(f["symbol"])
                    basis.pop(f["symbol"], None)
        return ShadowPortfolioState(
            cash=cash, positions=positions, cost_basis=basis, fees_paid=fees,
            realized_pnl=realized, turnover=turnover, fills=n,
        )

    def reconcile(self, session_id: str) -> dict[str, Any]:
        """Check the book against its own history. Fail closed on mismatch.

        Financial history is never silently repaired: a mismatch flips the session
        to RECONCILIATION_REQUIRED and the caller must stop, not continue.
        """
        problems: list[str] = []
        try:
            state = self.derive_portfolio(session_id)
        except ShadowReconciliationError as exc:
            self.set_status(session_id, ShadowSessionStatus.RECONCILIATION_REQUIRED)
            return {"ok": False, "problems": [str(exc)], "state": None}

        if state.cash < 0:
            problems.append(f"negative shadow cash {state.cash}")
        for sym, qty in state.positions.items():
            if qty < 0:
                problems.append(f"negative position {sym} {qty}")

        fill_seqs = {f["seq"] for f in self.fills(session_id)}
        order_seqs = {e["seq"] for e in self.events(session_id, ShadowEventKind.HYPOTHETICAL_FILL)}
        orphan = fill_seqs - order_seqs
        if orphan:
            problems.append(f"fills without a recorded fill event: {sorted(orphan)}")

        if problems:
            self.set_status(session_id, ShadowSessionStatus.RECONCILIATION_REQUIRED)
            return {"ok": False, "problems": problems, "state": state}
        return {"ok": True, "problems": [], "state": state}

    # ── decision quality ────────────────────────────────────────────────────
    def metrics(self, session_id: str, price_map: dict[str, Any] | None = None) -> dict[str, Any]:
        """Decision quality, not just PnL. Absent inputs stay None, never 0."""
        session = self.get_session(session_id)
        if session is None:
            raise ShadowError(f"unknown shadow session {session_id}")
        state = self.derive_portfolio(session_id)
        opening = Decimal(session["opening_cash"])

        nav: Decimal | None
        try:
            nav = state.nav(price_map) if price_map is not None else None
        except ShadowError:
            nav = None  # an unpriced position makes NAV unknown, not wrong

        counts: dict[str, int] = {}
        for e in self.events(session_id):
            counts[e["kind"]] = counts.get(e["kind"], 0) + 1

        cfs = self.counterfactuals(session_id)
        measured = [c for c in cfs if c["forward_pnl"] is not None]
        avoided = sum((c["forward_pnl"] for c in measured), Decimal("0"))

        return {
            "session_id": session_id,
            "mode": session["mode"],
            "status": session["status"],
            "opening_cash": opening,
            "cash": state.cash,
            "positions": dict(state.positions),
            "fills": state.fills,
            "fees_paid": state.fees_paid,
            "realized_pnl": state.realized_pnl,
            "turnover": state.turnover,
            "nav": nav,
            "net_return": ((nav - opening) / opening) if (nav is not None and opening) else None,
            "cost_drag": (state.fees_paid / state.turnover) if state.turnover else None,
            "signals": counts.get(ShadowEventKind.SIGNAL.value, 0),
            "intents": counts.get(ShadowEventKind.INTENT.value, 0),
            "guardian_events": counts.get(ShadowEventKind.GUARDIAN.value, 0),
            "guardian_blocks": len(cfs),
            "blocked_measured": len(measured),
            # Positive means the blocked trades WOULD have made money — Guardian
            # cost us. Negative means it protected us. Reported either way.
            "blocked_forward_pnl": avoided if measured else None,
            "degradations": counts.get(ShadowEventKind.DEGRADATION.value, 0),
            # Structural, and asserted by tests.
            "real_order_attempts": 0,
            "private_api_calls": 0,
            "real_ledger_mutations": 0,
        }

    def resume(self, session_id: str) -> dict[str, Any]:
        """Recover a session after a restart.

        Returns where to continue from. A session left in RECONCILIATION_REQUIRED
        is NOT resumable — the operator must look at it first.
        """
        session = self.get_session(session_id)
        if session is None:
            raise ShadowError(f"unknown shadow session {session_id}")
        if session["status"] == ShadowSessionStatus.RECONCILIATION_REQUIRED.value:
            raise ShadowReconciliationError(
                f"{session_id} needs reconciliation before it can resume"
            )
        rec = self.reconcile(session_id)
        if not rec["ok"]:
            raise ShadowReconciliationError(f"{session_id}: {'; '.join(rec['problems'])}")
        return {
            "session_id": session_id,
            "status": session["status"],
            "next_seq": self.next_seq(session_id),
            "state": rec["state"],
            "strategy_version": session["strategy_version"],
            "policy_versions": session["policy_versions"],
        }


def assert_no_execution_authority(obj: Any) -> None:
    """Refuse anything that would give a shadow record the power to execute.

    Called at the boundary. A shadow order carrying a venue, a broker client or a
    submit callable is not a shadow order — it is a live order wearing the name.
    """
    forbidden = ("submit", "execute", "send", "place_order", "client", "broker",
                 "venue_client", "api_key", "account_id", "credentials")
    for attr in forbidden:
        if hasattr(obj, attr):
            raise ShadowAuthorityError(
                f"shadow object carries execution-capable attribute {attr!r}"
            )
