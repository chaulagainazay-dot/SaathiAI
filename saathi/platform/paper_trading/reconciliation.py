"""M62.6 — durable reconciliation, drift detection, recovery orchestration,
and controlled repair planning for the paper-trading platform.

This subsystem is the AUTHORITATIVE INTEGRITY VERIFIER. It is read-mostly and
FAIL-CLOSED: it recomputes expected account state from the *immutable* event
record (fills + starting cash + reservations), compares it against persisted
state, classifies any drift, and produces immutable reconciliation reports.

It NEVER silently repairs accounting. The only state it may change is a
protective one — halting an affected paper account when CRITICAL drift is found
(a fail-closed safety action, analogous to a circuit breaker). Corrective repairs
are only ever *planned*: a RepairPlan describes root cause, corrective action,
expected state, evidence, and the approval scope required. There is no code path
in this module that applies a repair to financial state — authorization marks a
plan AUTHORIZED but execution is deliberately out of scope.

Boundaries (unchanged): PAPER only, long-only, no live broker, no credentials, no
network, no new execution authority. Everything is tenant-scoped by ``org_id``.
"""
from __future__ import annotations

import json
import time as _time
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any

from saathi.platform.context import PlatformContextError
from saathi.platform.models import PlatformPermission, new_id
from saathi.platform.trading_models import OrderSide
from saathi.platform.paper_trading.models import (
    PaperAccount, AccountStatus, D, q2, q6, _hash,
)
from saathi.platform.paper_trading.store import PaperStore


# ── severity + dimensions ─────────────────────────────────────────────────────
class DriftSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


_SEV_ORDER = {DriftSeverity.INFO: 0, DriftSeverity.WARNING: 1,
              DriftSeverity.ERROR: 2, DriftSeverity.CRITICAL: 3}


def sev_max(a: DriftSeverity, b: DriftSeverity) -> DriftSeverity:
    return a if _SEV_ORDER[a] >= _SEV_ORDER[b] else b


class ReconDimension(str, Enum):
    ORDERS_FILLS = "orders_fills"
    FILLS_POSITIONS = "fills_positions"
    POSITIONS_LEDGER = "positions_ledger"
    LEDGER_CASH = "ledger_cash"
    CASH_EQUITY = "cash_equity"
    RESERVATIONS_BALANCES = "reservations_balances"
    AUDIT_RUNTIME = "audit_runtime"


class RepairPlanStatus(str, Enum):
    PROPOSED = "PROPOSED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    AUTHORIZED = "AUTHORIZED"       # authorized != executed — execution is out of scope
    REJECTED = "REJECTED"


# ── findings / reports / repair plans ─────────────────────────────────────────
@dataclass
class DriftFinding:
    dimension: ReconDimension
    code: str
    severity: DriftSeverity
    message: str
    expected: str = ""
    actual: str = ""
    evidence: list[str] = field(default_factory=list)

    def to_public(self) -> dict[str, Any]:
        return {"dimension": self.dimension.value, "code": self.code, "severity": self.severity.value,
                "message": self.message, "expected": self.expected, "actual": self.actual,
                "evidence": list(self.evidence)}


@dataclass
class RepairPlan:
    plan_id: str
    run_id: str
    org_id: str
    account_id: str
    finding_code: str
    root_cause: str
    corrective_action: str
    expected_state: dict[str, Any]
    evidence: list[str]
    approval_scope: str
    status: RepairPlanStatus = RepairPlanStatus.PROPOSED
    created_at: float = 0.0
    acknowledged_by: str = ""
    acknowledged_at: float = 0.0
    authorized_by: str = ""
    authorized_at: float = 0.0
    note: str = ""

    def to_public(self) -> dict[str, Any]:
        return {"plan_id": self.plan_id, "run_id": self.run_id, "account_id": self.account_id,
                "finding_code": self.finding_code, "root_cause": self.root_cause,
                "corrective_action": self.corrective_action, "expected_state": self.expected_state,
                "evidence": list(self.evidence), "approval_scope": self.approval_scope,
                "status": self.status.value, "created_at": self.created_at,
                "acknowledged_by": self.acknowledged_by, "acknowledged_at": self.acknowledged_at,
                "authorized_by": self.authorized_by, "authorized_at": self.authorized_at,
                "note": self.note,
                "executes_automatically": False}


@dataclass
class ReconciliationReport:
    run_id: str
    org_id: str
    account_id: str
    ts: float
    severity_max: DriftSeverity
    findings: list[DriftFinding]
    expected_state: dict[str, Any]
    persisted_state: dict[str, Any]
    halted: bool
    repair_plan_ids: list[str]
    report_hash: str

    def counts(self) -> dict[str, int]:
        c = {s.value: 0 for s in DriftSeverity}
        for f in self.findings:
            c[f.severity.value] += 1
        return c

    def is_clean(self) -> bool:
        return self.severity_max == DriftSeverity.INFO and not any(
            f.severity != DriftSeverity.INFO for f in self.findings)

    def to_public(self) -> dict[str, Any]:
        return {"run_id": self.run_id, "account_id": self.account_id, "ts": self.ts,
                "severity_max": self.severity_max.value, "counts": self.counts(),
                "clean": self.is_clean(), "halted": self.halted,
                "findings": [f.to_public() for f in self.findings],
                "expected_state": self.expected_state, "persisted_state": self.persisted_state,
                "repair_plan_ids": list(self.repair_plan_ids), "report_hash": self.report_hash}


# ── persistence (shares the PaperStore SQLite connection, tenant-scoped) ───────
_RECON_SCHEMA = """
CREATE TABLE IF NOT EXISTS recon_runs (
    run_id TEXT PRIMARY KEY, org_id TEXT NOT NULL, account_id TEXT NOT NULL, ts REAL NOT NULL,
    severity_max TEXT NOT NULL, info_count INTEGER NOT NULL DEFAULT 0, warning_count INTEGER NOT NULL DEFAULT 0,
    error_count INTEGER NOT NULL DEFAULT 0, critical_count INTEGER NOT NULL DEFAULT 0,
    halted INTEGER NOT NULL DEFAULT 0, report_hash TEXT NOT NULL, report_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS recon_findings (
    id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL, org_id TEXT NOT NULL, account_id TEXT NOT NULL,
    dimension TEXT NOT NULL, code TEXT NOT NULL, severity TEXT NOT NULL, message TEXT NOT NULL,
    expected TEXT NOT NULL DEFAULT '', actual TEXT NOT NULL DEFAULT '', evidence_json TEXT NOT NULL DEFAULT '[]',
    ts REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS recon_recovery_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT, org_id TEXT NOT NULL, account_id TEXT NOT NULL,
    kind TEXT NOT NULL, detail_json TEXT NOT NULL DEFAULT '{}', ts REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS recon_repair_plans (
    plan_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, org_id TEXT NOT NULL, account_id TEXT NOT NULL,
    finding_code TEXT NOT NULL, root_cause TEXT NOT NULL, corrective_action TEXT NOT NULL,
    expected_state_json TEXT NOT NULL DEFAULT '{}', evidence_json TEXT NOT NULL DEFAULT '[]',
    approval_scope TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'PROPOSED', created_at REAL NOT NULL,
    acknowledged_by TEXT NOT NULL DEFAULT '', acknowledged_at REAL NOT NULL DEFAULT 0,
    authorized_by TEXT NOT NULL DEFAULT '', authorized_at REAL NOT NULL DEFAULT 0, note TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_rr_acct ON recon_runs(org_id, account_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_rf_run ON recon_findings(org_id, run_id);
CREATE INDEX IF NOT EXISTS idx_rre_acct ON recon_recovery_events(org_id, account_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_rp_acct ON recon_repair_plans(org_id, account_id, created_at DESC);
"""


class ReconStore:
    """Owns the reconciliation tables. Reuses the PaperStore connection so recon
    writes and (protective) account halts are atomic and share the same DB file."""

    def __init__(self, paper_store: PaperStore):
        self.paper = paper_store
        self._conn = paper_store._conn
        self._lock = paper_store._lock
        with self._lock, self._conn:
            self._conn.executescript(_RECON_SCHEMA)

    def _now(self) -> float:
        return _time.time()

    def save_run(self, report: ReconciliationReport) -> None:
        c = report.counts()
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO recon_runs (run_id,org_id,account_id,ts,severity_max,info_count,warning_count,"
                "error_count,critical_count,halted,report_hash,report_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (report.run_id, report.org_id, report.account_id, report.ts, report.severity_max.value,
                 c["INFO"], c["WARNING"], c["ERROR"], c["CRITICAL"], 1 if report.halted else 0,
                 report.report_hash, json.dumps(report.to_public(), default=str, sort_keys=True)))
            for f in report.findings:
                self._conn.execute(
                    "INSERT INTO recon_findings (run_id,org_id,account_id,dimension,code,severity,message,"
                    "expected,actual,evidence_json,ts) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (report.run_id, report.org_id, report.account_id, f.dimension.value, f.code,
                     f.severity.value, f.message, f.expected, f.actual,
                     json.dumps(f.evidence, default=str), report.ts))

    def save_repair_plan(self, p: RepairPlan) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO recon_repair_plans (plan_id,run_id,org_id,account_id,finding_code,root_cause,"
                "corrective_action,expected_state_json,evidence_json,approval_scope,status,created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (p.plan_id, p.run_id, p.org_id, p.account_id, p.finding_code, p.root_cause, p.corrective_action,
                 json.dumps(p.expected_state, default=str, sort_keys=True), json.dumps(p.evidence, default=str),
                 p.approval_scope, p.status.value, p.created_at))

    def record_recovery_event(self, org_id: str, account_id: str, kind: str, detail: dict) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO recon_recovery_events (org_id,account_id,kind,detail_json,ts) VALUES (?,?,?,?,?)",
                (org_id, account_id, kind, json.dumps(detail, default=str, sort_keys=True), self._now()))

    def get_run(self, org_id: str, run_id: str) -> dict | None:
        r = self._conn.execute("SELECT report_json FROM recon_runs WHERE org_id=? AND run_id=?",
                               (org_id, run_id)).fetchone()
        return json.loads(r["report_json"]) if r else None

    def list_runs(self, org_id: str, *, account_id: str | None = None, limit: int = 100) -> list[dict]:
        if account_id:
            rows = self._conn.execute(
                "SELECT run_id,account_id,ts,severity_max,info_count,warning_count,error_count,critical_count,"
                "halted FROM recon_runs WHERE org_id=? AND account_id=? ORDER BY ts DESC LIMIT ?",
                (org_id, account_id, int(limit))).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT run_id,account_id,ts,severity_max,info_count,warning_count,error_count,critical_count,"
                "halted FROM recon_runs WHERE org_id=? ORDER BY ts DESC LIMIT ?",
                (org_id, int(limit))).fetchall()
        return [dict(r) for r in rows]

    def list_recovery_events(self, org_id: str, account_id: str, *, limit: int = 100) -> list[dict]:
        rows = self._conn.execute(
            "SELECT kind,detail_json,ts FROM recon_recovery_events WHERE org_id=? AND account_id=? "
            "ORDER BY id DESC LIMIT ?", (org_id, account_id, int(limit))).fetchall()
        out = []
        for r in rows:
            d = dict(r); d["detail"] = json.loads(d.pop("detail_json") or "{}"); out.append(d)
        return out

    def get_repair_plan(self, org_id: str, plan_id: str) -> RepairPlan | None:
        r = self._conn.execute("SELECT * FROM recon_repair_plans WHERE org_id=? AND plan_id=?",
                               (org_id, plan_id)).fetchone()
        if not r:
            return None
        return RepairPlan(
            plan_id=r["plan_id"], run_id=r["run_id"], org_id=r["org_id"], account_id=r["account_id"],
            finding_code=r["finding_code"], root_cause=r["root_cause"], corrective_action=r["corrective_action"],
            expected_state=json.loads(r["expected_state_json"] or "{}"),
            evidence=json.loads(r["evidence_json"] or "[]"), approval_scope=r["approval_scope"],
            status=RepairPlanStatus(r["status"]), created_at=r["created_at"],
            acknowledged_by=r["acknowledged_by"], acknowledged_at=r["acknowledged_at"],
            authorized_by=r["authorized_by"], authorized_at=r["authorized_at"], note=r["note"])

    def list_repair_plans(self, org_id: str, *, account_id: str | None = None, limit: int = 100) -> list[dict]:
        if account_id:
            rows = self._conn.execute("SELECT plan_id FROM recon_repair_plans WHERE org_id=? AND account_id=? "
                                      "ORDER BY created_at DESC LIMIT ?", (org_id, account_id, int(limit))).fetchall()
        else:
            rows = self._conn.execute("SELECT plan_id FROM recon_repair_plans WHERE org_id=? "
                                      "ORDER BY created_at DESC LIMIT ?", (org_id, int(limit))).fetchall()
        return [self.get_repair_plan(org_id, r["plan_id"]).to_public() for r in rows]

    def update_repair_plan(self, org_id: str, plan_id: str, **fields) -> None:
        if not fields:
            return
        cols = ", ".join(f"{k}=?" for k in fields)
        with self._lock, self._conn:
            self._conn.execute(f"UPDATE recon_repair_plans SET {cols} WHERE org_id=? AND plan_id=?",
                               (*fields.values(), org_id, plan_id))


# ── corrective-action templates (planning only — never executed) ──────────────
_REPAIR_TEMPLATES = {
    "cash_mismatch": "Rebuild current_cash by replaying immutable fills from starting_cash; "
                     "do NOT overwrite fills. Requires operator authorization and a backup snapshot.",
    "position_mismatch": "Recompute position quantity as the signed sum of immutable fills; "
                         "correct the persisted position row only after authorization.",
    "reserved_mismatch": "Recompute reserved_cash/reserved_quantity from open (non-terminal) orders; "
                         "reconcile the persisted reservation after authorization.",
    "order_fill_mismatch": "Recompute order.filled_quantity from its immutable fills and reconcile "
                           "broker_state via the state machine after authorization.",
    "ledger_mismatch": "Rebuild the ledger projection from fills; the ledger is a derived audit trail, "
                       "so regenerate it (never the fills) after authorization.",
    "negative_balance": "Freeze the account (already halted), snapshot state, and manually investigate "
                        "the corrupting event before any correction is authorized.",
    "missing_transition": "Backfill the missing order transition record from fills/ledger history; "
                          "audit-only, no financial change.",
    "generic": "Investigate root cause, snapshot state, and prepare a replay-based correction. "
               "No automatic financial mutation.",
}


class ReconciliationEngine:
    """Integrity verifier + recovery orchestrator + repair planner.

    Reads from the PaperStore (immutable fills, orders, positions, ledger,
    transitions). Its only mutation is a protective account halt on CRITICAL
    drift. Repairs are planned, never executed.
    """

    def __init__(self, paper_store: PaperStore, *, platform_store=None, tol: Decimal = Decimal("0.01")):
        self.paper = paper_store
        self.store = ReconStore(paper_store)
        self._platform_store = platform_store   # optional audit sink
        self.tol = D(tol)

    def bind_audit(self, platform_store):
        self._platform_store = platform_store
        return self

    def _audit(self, ctx, event, **detail):
        if not self._platform_store:
            return
        try:
            self._platform_store.append_audit(event, org_id=ctx.org_id, workspace_id=ctx.workspace_id,
                                              user_id=ctx.user_id, role=ctx.role,
                                              outcome=detail.pop("outcome", "ok"), detail=detail)
        except Exception:
            pass

    # ── recompute expected state from the immutable event record ──────────────
    def recompute_expected(self, org_id: str, account_id: str) -> dict[str, Any]:
        """Deterministically rebuild account state from starting_cash + immutable
        fills + open-order reservations. Pure function of persisted events; no writes.
        Ordering is deterministic: (created_at, paper_order_id, seq)."""
        acct = self.paper.get_account(org_id, account_id)
        if not acct:
            raise PlatformContextError("NOT_FOUND", "paper account not found for tenant")
        orders = self.paper.list_orders(org_id, account_id=account_id, limit=500)

        fills: list[dict] = []
        for o in orders:
            for f in self.paper.list_fills(org_id, o.id):
                fills.append({**f, "_order_id": o.id})
        fills.sort(key=lambda f: (f.get("created_at", 0.0), f["paper_order_id"], f.get("seq", 0)))

        cash = D(acct.starting_cash)
        realized = Decimal("0")
        pos: dict[str, dict] = {}   # symbol -> {qty, avg_cost, realized}
        filled_by_order: dict[str, Decimal] = {}

        for f in fills:
            sym = None
            for o in orders:
                if o.id == f["paper_order_id"]:
                    sym = o.symbol
                    break
            qty = D(f["quantity"]); price = D(f["price"]); gross = D(f["gross_amount"]); fee = D(f["fee"])
            filled_by_order[f["paper_order_id"]] = filled_by_order.get(f["paper_order_id"], Decimal("0")) + qty
            p = pos.setdefault(sym, {"qty": Decimal("0"), "avg_cost": Decimal("0"), "realized": Decimal("0")})
            if f["side"] == OrderSide.BUY.value:
                cash = q2(cash - q2(gross + fee))
                new_qty = p["qty"] + qty
                p["avg_cost"] = q6((p["avg_cost"] * p["qty"] + gross) / new_qty) if new_qty > 0 else Decimal("0")
                p["qty"] = new_qty
            else:  # SELL
                r = q2((price - p["avg_cost"]) * qty)
                p["realized"] = q2(p["realized"] + r)
                realized = q2(realized + r)
                cash = q2(cash + q2(gross - fee))
                p["qty"] = p["qty"] - qty
                if p["qty"] == 0:
                    p["avg_cost"] = Decimal("0")

        # reservations recomputed from OPEN (non-terminal) orders
        reserved_cash = Decimal("0")
        reserved_qty: dict[str, Decimal] = {}
        for o in orders:
            if o.is_terminal:
                continue
            reserved_cash = q2(reserved_cash + D(o.reserved_cash))
            if o.side == OrderSide.SELL and o.reserved_quantity:
                reserved_qty[o.symbol] = reserved_qty.get(o.symbol, Decimal("0")) + D(o.reserved_quantity)

        positions_value = sum((p["qty"] * p["avg_cost"] for p in pos.values() if p["qty"] != 0), Decimal("0"))
        equity = q2(cash + positions_value)

        return {
            "account_id": account_id,
            "cash": str(q2(cash)),
            "reserved_cash": str(q2(reserved_cash)),
            "available_cash": str(q2(cash - reserved_cash)),
            "realized_pnl": str(q2(realized)),
            "equity": str(equity),
            "positions": {s: {"quantity": str(p["qty"]), "avg_cost": str(q6(p["avg_cost"])),
                              "realized_pnl": str(q2(p["realized"])),
                              "reserved_quantity": str(reserved_qty.get(s, Decimal("0")))}
                          for s, p in sorted(pos.items())},
            "filled_by_order": {k: str(v) for k, v in sorted(filled_by_order.items())},
            "fill_count": len(fills),
        }

    def _persisted_state(self, org_id: str, acct: PaperAccount) -> dict[str, Any]:
        positions = self.paper.list_positions(org_id, acct.id)
        pv = sum((p.quantity * p.avg_cost for p in positions if p.quantity != 0), Decimal("0"))
        return {
            "account_id": acct.id,
            "cash": str(q2(acct.current_cash)),
            "reserved_cash": str(q2(acct.reserved_cash)),
            "available_cash": str(acct.available_cash),
            "realized_pnl": str(q2(acct.realized_pnl)),
            "equity": str(q2(acct.current_cash + pv)),
            "status": acct.status.value,
            "positions": {p.symbol: {"quantity": str(p.quantity), "avg_cost": str(q6(p.avg_cost)),
                                     "realized_pnl": str(q2(p.realized_pnl)),
                                     "reserved_quantity": str(p.reserved_quantity)}
                          for p in sorted(positions, key=lambda x: x.symbol)},
        }

    # ── the reconciliation pass ───────────────────────────────────────────────
    def reconcile_account(self, ctx, account_id: str) -> ReconciliationReport:
        ctx.require_permission(PlatformPermission.RECONCILE_RUN)
        acct = self.paper.get_account(ctx.org_id, account_id)
        if not acct:
            raise PlatformContextError("NOT_FOUND", "paper account not found for tenant")

        expected = self.recompute_expected(ctx.org_id, account_id)
        persisted = self._persisted_state(ctx.org_id, acct)
        findings: list[DriftFinding] = []

        orders = self.paper.list_orders(ctx.org_id, account_id=account_id, limit=500)
        positions = {p.symbol: p for p in self.paper.list_positions(ctx.org_id, account_id)}
        ledger = self.paper.list_ledger(ctx.org_id, account_id, limit=5000)
        tol = self.tol

        def near(a: Decimal, b: Decimal) -> bool:
            return abs(D(a) - D(b)) <= tol

        # D1 ORDERS ↔ FILLS
        for o in orders:
            exp_filled = D(expected["filled_by_order"].get(o.id, "0"))
            if not near(exp_filled, o.filled_quantity):
                findings.append(DriftFinding(
                    ReconDimension.ORDERS_FILLS, "order_fill_mismatch", DriftSeverity.ERROR,
                    f"order {o.id} filled_quantity disagrees with immutable fills",
                    expected=str(exp_filled), actual=str(o.filled_quantity), evidence=[f"order:{o.id}"]))
            # state-machine consistency
            if o.filled_quantity > 0 and o.remaining_quantity <= 0 and \
                    o.broker_state.value not in ("FILLED", "CANCELLED"):
                findings.append(DriftFinding(
                    ReconDimension.ORDERS_FILLS, "order_state_mismatch", DriftSeverity.ERROR,
                    f"order {o.id} fully filled but state={o.broker_state.value}",
                    expected="FILLED", actual=o.broker_state.value, evidence=[f"order:{o.id}"]))

        # D2 FILLS ↔ POSITIONS
        exp_pos = expected["positions"]
        seen_syms = set(exp_pos) | set(positions)
        for sym in sorted(seen_syms):
            exp_qty = D(exp_pos.get(sym, {}).get("quantity", "0"))
            act_qty = positions[sym].quantity if sym in positions else Decimal("0")
            if not near(exp_qty, act_qty):
                findings.append(DriftFinding(
                    ReconDimension.FILLS_POSITIONS, "position_mismatch", DriftSeverity.CRITICAL,
                    f"{sym} position quantity disagrees with signed sum of immutable fills",
                    expected=str(exp_qty), actual=str(act_qty), evidence=[f"position:{sym}"]))
            if sym in positions and positions[sym].quantity < -tol:
                findings.append(DriftFinding(
                    ReconDimension.FILLS_POSITIONS, "negative_position", DriftSeverity.CRITICAL,
                    f"{sym} position is negative (long-only violated)",
                    expected=">=0", actual=str(positions[sym].quantity), evidence=[f"position:{sym}"]))

        # D3 POSITIONS ↔ LEDGER  (each fill emits a buy/sell + a fee ledger row)
        fill_rows = sum(1 for e in ledger if e["kind"] in ("buy", "sell"))
        if fill_rows != expected["fill_count"]:
            findings.append(DriftFinding(
                ReconDimension.POSITIONS_LEDGER, "ledger_fill_count_mismatch", DriftSeverity.ERROR,
                "ledger buy/sell rows disagree with immutable fill count",
                expected=str(expected["fill_count"]), actual=str(fill_rows), evidence=["ledger"]))

        # D4 LEDGER ↔ CASH  (starting_cash + cash-affecting ledger == current_cash)
        cash_delta = sum((D(e["amount"]) for e in ledger if e["kind"] in ("buy", "sell", "fee")), Decimal("0"))
        ledger_cash = q2(D(acct.starting_cash) + cash_delta)
        if not near(ledger_cash, acct.current_cash):
            findings.append(DriftFinding(
                ReconDimension.LEDGER_CASH, "ledger_cash_mismatch", DriftSeverity.ERROR,
                "current_cash disagrees with starting_cash + ledger cash movements",
                expected=str(ledger_cash), actual=str(q2(acct.current_cash)), evidence=["ledger"]))
        if ledger:
            last_balance = D(ledger[-1]["balance_after"])
            if not near(last_balance, acct.current_cash):
                findings.append(DriftFinding(
                    ReconDimension.LEDGER_CASH, "ledger_balance_after_mismatch", DriftSeverity.WARNING,
                    "last ledger balance_after disagrees with current_cash",
                    expected=str(q2(acct.current_cash)), actual=str(last_balance), evidence=["ledger"]))

        # authoritative cash: recomputed-from-fills vs persisted  → CRITICAL if off
        if not near(D(expected["cash"]), acct.current_cash):
            findings.append(DriftFinding(
                ReconDimension.LEDGER_CASH, "cash_mismatch", DriftSeverity.CRITICAL,
                "current_cash disagrees with cash recomputed from immutable fills",
                expected=expected["cash"], actual=str(q2(acct.current_cash)), evidence=["fills", f"account:{acct.id}"]))

        # D5 CASH ↔ EQUITY
        if not near(D(expected["equity"]), D(persisted["equity"])):
            findings.append(DriftFinding(
                ReconDimension.CASH_EQUITY, "equity_mismatch", DriftSeverity.ERROR,
                "persisted equity disagrees with recomputed equity",
                expected=expected["equity"], actual=persisted["equity"], evidence=[f"account:{acct.id}"]))
        if acct.available_cash < -tol:
            findings.append(DriftFinding(
                ReconDimension.CASH_EQUITY, "negative_available_cash", DriftSeverity.CRITICAL,
                "available cash is negative", expected=">=0", actual=str(acct.available_cash),
                evidence=[f"account:{acct.id}"]))

        # D6 RESERVATIONS ↔ BALANCES
        if not near(D(expected["reserved_cash"]), acct.reserved_cash):
            findings.append(DriftFinding(
                ReconDimension.RESERVATIONS_BALANCES, "reserved_mismatch", DriftSeverity.ERROR,
                "reserved_cash disagrees with sum of open-order reservations",
                expected=expected["reserved_cash"], actual=str(q2(acct.reserved_cash)),
                evidence=[f"account:{acct.id}"]))
        if acct.reserved_cash < -tol:
            findings.append(DriftFinding(
                ReconDimension.RESERVATIONS_BALANCES, "negative_reserved_cash", DriftSeverity.CRITICAL,
                "reserved cash is negative", expected=">=0", actual=str(q2(acct.reserved_cash)),
                evidence=[f"account:{acct.id}"]))
        if acct.reserved_cash > acct.current_cash + tol:
            findings.append(DriftFinding(
                ReconDimension.RESERVATIONS_BALANCES, "reserved_exceeds_cash", DriftSeverity.CRITICAL,
                "reserved cash exceeds current cash", expected=f"<= {q2(acct.current_cash)}",
                actual=str(q2(acct.reserved_cash)), evidence=[f"account:{acct.id}"]))
        for sym, p in positions.items():
            exp_rq = D(exp_pos.get(sym, {}).get("reserved_quantity", "0"))
            if not near(exp_rq, p.reserved_quantity):
                findings.append(DriftFinding(
                    ReconDimension.RESERVATIONS_BALANCES, "reserved_qty_mismatch", DriftSeverity.ERROR,
                    f"{sym} reserved_quantity disagrees with open SELL orders",
                    expected=str(exp_rq), actual=str(p.reserved_quantity), evidence=[f"position:{sym}"]))
            if p.reserved_quantity > p.quantity + tol:
                findings.append(DriftFinding(
                    ReconDimension.RESERVATIONS_BALANCES, "reserved_qty_exceeds_holding", DriftSeverity.CRITICAL,
                    f"{sym} reserved quantity exceeds holding", expected=f"<= {p.quantity}",
                    actual=str(p.reserved_quantity), evidence=[f"position:{sym}"]))

        # D7 AUDIT ↔ RUNTIME  (every order must have a transition trail)
        for o in orders:
            trans = self.paper.list_transitions(ctx.org_id, o.id)
            if not trans:
                findings.append(DriftFinding(
                    ReconDimension.AUDIT_RUNTIME, "missing_transition", DriftSeverity.WARNING,
                    f"order {o.id} has no transition audit trail",
                    expected=">=1 transition", actual="0", evidence=[f"order:{o.id}"]))
            elif trans[-1]["to_state"] != o.broker_state.value and o.is_terminal:
                findings.append(DriftFinding(
                    ReconDimension.AUDIT_RUNTIME, "transition_state_mismatch", DriftSeverity.WARNING,
                    f"order {o.id} last transition != broker_state",
                    expected=o.broker_state.value, actual=trans[-1]["to_state"], evidence=[f"order:{o.id}"]))

        if not findings:
            findings.append(DriftFinding(
                ReconDimension.CASH_EQUITY, "clean", DriftSeverity.INFO,
                "all reconciliation dimensions agree with the immutable event record"))

        severity_max = DriftSeverity.INFO
        for f in findings:
            severity_max = sev_max(severity_max, f.severity)

        run_id = new_id("recon_")
        ts = _time.time()
        report_hash = _hash({"account": account_id, "expected": expected, "persisted": persisted,
                             "findings": [f.to_public() for f in findings]})

        # protective halt on CRITICAL (fail-closed; never a financial mutation)
        halted = False
        critical = [f for f in findings if f.severity == DriftSeverity.CRITICAL]
        if critical and acct.status == AccountStatus.ACTIVE:
            reason = "reconciliation:critical drift " + ",".join(sorted({f.code for f in critical}))
            kind, _ = self.paper.update_account_status(
                ctx.org_id, account_id, expected_version=acct.version,
                status=AccountStatus.HALTED, halt_reason=reason[:200])
            halted = kind == "ok"
            self.store.record_recovery_event(ctx.org_id, account_id, "critical_halt",
                                             {"run_id": run_id, "reason": reason, "applied": halted})
            self._audit(ctx, "reconciliation.account.halted", account_id=account_id, run_id=run_id,
                        reason=reason, outcome="halted")

        # repair plans for ERROR/CRITICAL findings (planned, never executed)
        repair_ids: list[str] = []
        for f in findings:
            if f.severity in (DriftSeverity.ERROR, DriftSeverity.CRITICAL):
                p = self._build_repair_plan(ctx.org_id, run_id, account_id, f, expected)
                self.store.save_repair_plan(p)
                repair_ids.append(p.plan_id)

        report = ReconciliationReport(
            run_id=run_id, org_id=ctx.org_id, account_id=account_id, ts=ts, severity_max=severity_max,
            findings=findings, expected_state=expected, persisted_state=persisted, halted=halted,
            repair_plan_ids=repair_ids, report_hash=report_hash)
        self.store.save_run(report)
        self._audit(ctx, "reconciliation.run", account_id=account_id, run_id=run_id,
                    severity_max=severity_max.value, halted=halted, findings=len(findings))
        return report

    def reconcile_all(self, ctx) -> list[ReconciliationReport]:
        ctx.require_permission(PlatformPermission.RECONCILE_RUN)
        return [self.reconcile_account(ctx, a.id) for a in self.paper.list_accounts(ctx.org_id)]

    def _build_repair_plan(self, org_id, run_id, account_id, finding: DriftFinding, expected: dict) -> RepairPlan:
        key = ("negative_balance" if finding.code.startswith("negative")
               else "cash_mismatch" if finding.code == "cash_mismatch"
               else "position_mismatch" if "position" in finding.code
               else "reserved_mismatch" if "reserved" in finding.code
               else "order_fill_mismatch" if finding.code.startswith("order")
               else "ledger_mismatch" if "ledger" in finding.code
               else "missing_transition" if "transition" in finding.code
               else "generic")
        return RepairPlan(
            plan_id=new_id("repair_"), run_id=run_id, org_id=org_id, account_id=account_id,
            finding_code=finding.code,
            root_cause=f"[{finding.dimension.value}] {finding.message} (expected={finding.expected}, actual={finding.actual})",
            corrective_action=_REPAIR_TEMPLATES.get(key, _REPAIR_TEMPLATES["generic"]),
            expected_state=expected, evidence=list(finding.evidence),
            approval_scope="OWNER:reconciliation.repair_authorize",
            status=RepairPlanStatus.PROPOSED, created_at=_time.time(),
            note="Repair plans are advisory. This subsystem never applies repairs automatically.")

    # ── recovery orchestration (deterministic; no financial mutation) ─────────
    def recover_account(self, ctx, account_id: str) -> dict[str, Any]:
        """Deterministic recovery: recompute expected state from the immutable
        event record and reconcile against persisted state. Proves integrity after
        restart / interruption / duplicate events. Never repairs silently."""
        ctx.require_permission(PlatformPermission.RECONCILE_RUN)
        expected = self.recompute_expected(ctx.org_id, account_id)
        report = self.reconcile_account(ctx, account_id)
        self.store.record_recovery_event(
            ctx.org_id, account_id, "recovery_scan",
            {"run_id": report.run_id, "severity_max": report.severity_max.value,
             "clean": report.is_clean(), "expected_hash": _hash(expected)})
        return {"account_id": account_id, "expected_state": expected,
                "reconciliation": report.to_public(),
                "deterministic": True, "silent_repair": False}

    # ── read APIs ─────────────────────────────────────────────────────────────
    def list_runs(self, ctx, *, account_id=None, limit=100) -> list[dict]:
        ctx.require_permission(PlatformPermission.RECONCILE_READ)
        return self.store.list_runs(ctx.org_id, account_id=account_id, limit=limit)

    def get_run(self, ctx, run_id: str) -> dict:
        ctx.require_permission(PlatformPermission.RECONCILE_READ)
        r = self.store.get_run(ctx.org_id, run_id)
        if not r:
            raise PlatformContextError("NOT_FOUND", "reconciliation run not found for tenant")
        return r

    def list_recovery_events(self, ctx, account_id: str, *, limit=100) -> list[dict]:
        ctx.require_permission(PlatformPermission.RECONCILE_READ)
        return self.store.list_recovery_events(ctx.org_id, account_id, limit=limit)

    def list_repair_plans(self, ctx, *, account_id=None, limit=100) -> list[dict]:
        ctx.require_permission(PlatformPermission.RECONCILE_READ)
        return self.store.list_repair_plans(ctx.org_id, account_id=account_id, limit=limit)

    def get_repair_plan(self, ctx, plan_id: str) -> dict:
        ctx.require_permission(PlatformPermission.RECONCILE_READ)
        p = self.store.get_repair_plan(ctx.org_id, plan_id)
        if not p:
            raise PlatformContextError("NOT_FOUND", "repair plan not found for tenant")
        return p.to_public()

    # ── operator acknowledgement / authorization (metadata only) ──────────────
    def acknowledge_repair_plan(self, ctx, plan_id: str) -> dict:
        ctx.require_permission(PlatformPermission.REPAIR_PLAN_ACKNOWLEDGE)
        p = self.store.get_repair_plan(ctx.org_id, plan_id)
        if not p:
            raise PlatformContextError("NOT_FOUND", "repair plan not found for tenant")
        if p.status != RepairPlanStatus.PROPOSED:
            raise PlatformContextError("VALIDATION_FAILED", f"cannot acknowledge from {p.status.value}")
        self.store.update_repair_plan(ctx.org_id, plan_id, status=RepairPlanStatus.ACKNOWLEDGED.value,
                                      acknowledged_by=ctx.user_id, acknowledged_at=_time.time())
        self._audit(ctx, "reconciliation.repair.acknowledged", plan_id=plan_id, account_id=p.account_id)
        return self.store.get_repair_plan(ctx.org_id, plan_id).to_public()

    def authorize_repair_plan(self, ctx, plan_id: str) -> dict:
        """Authorize a repair plan. This marks intent ONLY — it does NOT execute a
        repair. There is deliberately no code path that mutates financial state from
        a plan; correction remains a manual, out-of-band operator action."""
        ctx.require_permission(PlatformPermission.REPAIR_PLAN_AUTHORIZE)
        p = self.store.get_repair_plan(ctx.org_id, plan_id)
        if not p:
            raise PlatformContextError("NOT_FOUND", "repair plan not found for tenant")
        if p.status != RepairPlanStatus.ACKNOWLEDGED:
            raise PlatformContextError("VALIDATION_FAILED",
                                       "repair plan must be ACKNOWLEDGED before authorization")
        self.store.update_repair_plan(
            ctx.org_id, plan_id, status=RepairPlanStatus.AUTHORIZED.value,
            authorized_by=ctx.user_id, authorized_at=_time.time(),
            note="Authorized for manual correction. Engine performs NO automatic repair.")
        self._audit(ctx, "reconciliation.repair.authorized", plan_id=plan_id, account_id=p.account_id,
                    outcome="authorized_not_executed")
        return self.store.get_repair_plan(ctx.org_id, plan_id).to_public()

    def reject_repair_plan(self, ctx, plan_id: str, *, reason: str = "") -> dict:
        ctx.require_permission(PlatformPermission.REPAIR_PLAN_ACKNOWLEDGE)
        p = self.store.get_repair_plan(ctx.org_id, plan_id)
        if not p:
            raise PlatformContextError("NOT_FOUND", "repair plan not found for tenant")
        self.store.update_repair_plan(ctx.org_id, plan_id, status=RepairPlanStatus.REJECTED.value,
                                      note=f"rejected: {reason}"[:200])
        self._audit(ctx, "reconciliation.repair.rejected", plan_id=plan_id, account_id=p.account_id)
        return self.store.get_repair_plan(ctx.org_id, plan_id).to_public()
