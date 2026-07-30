"""M229 — Account Snapshot and Reconciliation Contracts (read models).

Normalized schemas for simulated account data. No execution commands.
"""
from __future__ import annotations

import json
import time
from typing import Any

from saathi.platform.tg.broker_readiness.models import ReconciliationClass
from saathi.platform.tg.broker_readiness.store import ReadinessStore, _uid, evidence_hash


class SnapshotError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


def default_fixture_snapshot(provider_id: str = "sim.readonly.fixture") -> dict[str, Any]:
    now = time.time()
    return {
        "provider": provider_id,
        "account_reference": "sim-acct-001",
        "account_type": "SIMULATED_READ_ONLY",
        "status": "ACTIVE_SIM",
        "base_currency": "USD",
        "permissions": [
            "ACCOUNT_METADATA_READ", "BALANCE_READ", "POSITION_READ", "PORTFOLIO_READ",
        ],
        "balances": [
            {
                "asset": "USD", "total": "100000.00", "available": "95000.00",
                "locked": "5000.00", "borrowed": "0", "interest": "0",
                "valuation_reference": "USD",
            },
            {
                "asset": "BTC", "total": "0.50000000", "available": "0.50000000",
                "locked": "0", "borrowed": "0", "interest": "0",
                "valuation_reference": "USD",
            },
        ],
        "positions": [
            {
                "instrument": "AAPL", "quantity": "10", "average_entry": "180.00",
                "mark_price": "185.00", "unrealized_pnl": "50.00", "realized_pnl": "0",
                "position_side": "LONG", "leverage_metadata": {"leverage": "1"},
                "margin_metadata": {}, "update_timestamp": now,
            },
        ],
        "open_order_count": 0,
        "historical_order_count": 3,
        "trade_count": 3,
        "fees": [{"asset": "USD", "amount": "1.50"}],
        "liabilities": [],
        "margin_metadata": {"enabled": False},
        "snapshot_timestamp": now,
        "provider_timestamp": now - 0.1,
        "ingestion_timestamp": now,
        "history": {
            "orders": [{"id": "ord-1", "symbol": "AAPL", "side": "BUY", "qty": "10"}],
            "fills": [{"id": "fill-1", "order_id": "ord-1", "qty": "10", "price": "180.00"}],
            "trades": [{"id": "tr-1", "symbol": "AAPL", "qty": "10", "price": "180.00"}],
            "fees": [{"id": "fee-1", "amount": "1.50"}],
            "deposits": [{"id": "dep-1", "asset": "USD", "amount": "100000.00"}],
            "withdrawals": [],
            "transfers": [],
        },
    }


class AccountSnapshotService:
    def __init__(self, store: ReadinessStore):
        self.store = store

    def load_fixture(
        self,
        provider_id: str = "sim.readonly.fixture",
        *,
        override: dict | None = None,
    ) -> dict[str, Any]:
        data = default_fixture_snapshot(provider_id)
        if override:
            data = {**data, **override}
        return self.ingest(data)

    def ingest(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        """Ingest simulated snapshot as read model. Never creates execution commands."""
        now = time.time()
        sid = _uid("snap")
        fp = evidence_hash({
            k: snapshot.get(k) for k in (
                "provider", "account_reference", "balances", "positions",
                "snapshot_timestamp",
            )
        })
        self.store.execute(
            """INSERT INTO br_account_snapshots(
                id, provider_id, account_ref, account_type, status, base_currency,
                permissions_json, balances_json, positions_json, open_order_count,
                historical_order_count, trade_count, fees_json, liabilities_json,
                margin_json, history_json, snapshot_ts, provider_ts, ingestion_ts,
                source_fingerprint, detail_json, created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                sid,
                snapshot.get("provider", "sim.readonly.fixture"),
                snapshot.get("account_reference", "sim-acct"),
                snapshot.get("account_type", "SIMULATED"),
                snapshot.get("status", "ACTIVE_SIM"),
                snapshot.get("base_currency", "USD"),
                json.dumps(snapshot.get("permissions") or []),
                json.dumps(snapshot.get("balances") or []),
                json.dumps(snapshot.get("positions") or []),
                int(snapshot.get("open_order_count") or 0),
                int(snapshot.get("historical_order_count") or 0),
                int(snapshot.get("trade_count") or 0),
                json.dumps(snapshot.get("fees") or []),
                json.dumps(snapshot.get("liabilities") or []),
                json.dumps(snapshot.get("margin_metadata") or {}),
                json.dumps(snapshot.get("history") or {}),
                float(snapshot.get("snapshot_timestamp") or now),
                float(snapshot.get("provider_timestamp") or now),
                float(snapshot.get("ingestion_timestamp") or now),
                fp,
                json.dumps({"read_model_only": True, "execution_commands": False}),
                now,
            ),
        )
        self.store.audit("snapshot.ingested", subject=sid, detail={
            "provider": snapshot.get("provider"), "fingerprint": fp,
        })
        return self.get(sid)

    def get(self, snapshot_id: str) -> dict[str, Any]:
        row = self.store.fetchone("SELECT * FROM br_account_snapshots WHERE id=?", (snapshot_id,))
        if not row:
            raise SnapshotError("SNAPSHOT_NOT_FOUND", snapshot_id)
        return self._public(row)

    def list_snapshots(self, provider_id: str = "") -> list[dict[str, Any]]:
        if provider_id:
            rows = self.store.fetchall(
                "SELECT * FROM br_account_snapshots WHERE provider_id=? ORDER BY created_at DESC",
                (provider_id,),
            )
        else:
            rows = self.store.fetchall(
                "SELECT * FROM br_account_snapshots ORDER BY created_at DESC LIMIT 50"
            )
        return [self._public(r) for r in rows]

    def _public(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row["id"],
            "provider": row["provider_id"],
            "account_reference": row["account_ref"],
            "account_type": row["account_type"],
            "status": row["status"],
            "base_currency": row["base_currency"],
            "permissions": json.loads(row["permissions_json"] or "[]"),
            "balances": json.loads(row["balances_json"] or "[]"),
            "positions": json.loads(row["positions_json"] or "[]"),
            "open_order_count": row["open_order_count"],
            "historical_order_count": row["historical_order_count"],
            "trade_count": row["trade_count"],
            "fees": json.loads(row["fees_json"] or "[]"),
            "liabilities": json.loads(row["liabilities_json"] or "[]"),
            "margin_metadata": json.loads(row["margin_json"] or "{}"),
            "history": json.loads(row["history_json"] or "{}"),
            "snapshot_timestamp": row["snapshot_ts"],
            "provider_timestamp": row["provider_ts"],
            "ingestion_timestamp": row["ingestion_ts"],
            "source_fingerprint": row["source_fingerprint"],
            "read_model_only": True,
            "execution_commands": False,
            "simulation_only": True,
        }


class ReconciliationEngine:
    """Compare snapshots. Recommendations only — never mutates provider or portfolio."""

    def __init__(self, store: ReadinessStore, snapshots: AccountSnapshotService):
        self.store = store
        self.snapshots = snapshots

    def reconcile(
        self,
        provider_snapshot_id: str,
        local_snapshot_id: str = "",
        *,
        paper_portfolio: dict | None = None,
        durable_ledger: dict | None = None,
    ) -> dict[str, Any]:
        provider = self.snapshots.get(provider_snapshot_id)
        local = self.snapshots.get(local_snapshot_id) if local_snapshot_id else None
        paper_portfolio = paper_portfolio or {}
        durable_ledger = durable_ledger or {}

        discrepancies: list[dict[str, Any]] = []
        classifications: list[str] = []

        def add(cls: ReconciliationClass, detail: str, **extra: Any) -> None:
            classifications.append(cls.value)
            discrepancies.append({"class": cls.value, "detail": detail, **extra})

        # Stale snapshot
        now = time.time()
        if now - provider["snapshot_timestamp"] > 3600:
            add(ReconciliationClass.STALE_SNAPSHOT, "provider snapshot older than 1h")

        # Permissions
        if any(s for s in provider["permissions"] if "CREATE" in s or "WITHDRAW" in s):
            add(ReconciliationClass.PERMISSION_MISMATCH, "provider snapshot has write-like permission")

        # Compare balances if local present
        if local:
            p_bal = {b["asset"]: b for b in provider["balances"]}
            l_bal = {b["asset"]: b for b in local["balances"]}
            for asset, pb in p_bal.items():
                if asset not in l_bal:
                    add(ReconciliationClass.MISSING_LOCAL_RECORD, f"asset {asset} missing locally")
                else:
                    try:
                        pt, lt = float(pb["total"]), float(l_bal[asset]["total"])
                        if abs(pt - lt) < 1e-8:
                            add(ReconciliationClass.MATCHED, f"balance {asset} matched")
                        elif abs(pt - lt) < 0.02:
                            add(ReconciliationClass.ROUNDING_DIFFERENCE, f"balance {asset} rounding")
                        else:
                            add(ReconciliationClass.CRITICAL_RECONCILIATION_FAILURE,
                                f"balance {asset} mismatch {pt} vs {lt}")
                    except (TypeError, ValueError):
                        add(ReconciliationClass.CRITICAL_RECONCILIATION_FAILURE, f"bad balance {asset}")
            for asset in l_bal:
                if asset not in p_bal:
                    add(ReconciliationClass.MISSING_PROVIDER_RECORD, f"asset {asset} missing on provider")

            # Timing
            if abs(provider["provider_timestamp"] - local["provider_timestamp"]) > 5:
                add(ReconciliationClass.TIMING_DIFFERENCE, "provider timestamps differ >5s")

            # Positions
            p_pos = {p["instrument"]: p for p in provider["positions"]}
            l_pos = {p["instrument"]: p for p in local["positions"]}
            for inst in set(p_pos) | set(l_pos):
                if inst not in p_pos:
                    add(ReconciliationClass.MISSING_PROVIDER_RECORD, f"position {inst}")
                elif inst not in l_pos:
                    add(ReconciliationClass.MISSING_LOCAL_RECORD, f"position {inst}")
                else:
                    try:
                        if float(p_pos[inst]["quantity"]) < 0 or float(l_pos[inst]["quantity"]) < 0:
                            add(ReconciliationClass.CRITICAL_RECONCILIATION_FAILURE,
                                f"impossible negative quantity {inst}")
                    except (TypeError, ValueError):
                        add(ReconciliationClass.CRITICAL_RECONCILIATION_FAILURE, f"bad qty {inst}")

            # History duplicates
            for kind in ("orders", "trades", "fills"):
                items = (provider.get("history") or {}).get(kind) or []
                ids = [i.get("id") for i in items if i.get("id")]
                if len(ids) != len(set(ids)):
                    add(ReconciliationClass.DUPLICATE_RECORD, f"duplicate {kind} in provider history")

        # Unknown assets
        known = {"USD", "BTC", "ETH", "AAPL", "EUR", "USDT"}
        for b in provider["balances"]:
            if b.get("asset") not in known:
                add(ReconciliationClass.UNKNOWN_ASSET, f"unknown asset {b.get('asset')}")

        # Paper portfolio / ledger comparison (recommendations only)
        recommendations: list[str] = []
        if paper_portfolio.get("cash") is not None:
            recommendations.append("Compare paper cash to provider USD available manually.")
        if durable_ledger:
            recommendations.append("Cross-check durable ledger entries offline; no auto-mutation.")

        if not classifications:
            classifications.append(ReconciliationClass.MATCHED.value)

        critical = ReconciliationClass.CRITICAL_RECONCILIATION_FAILURE.value in classifications
        overall = (
            ReconciliationClass.CRITICAL_RECONCILIATION_FAILURE.value
            if critical
            else (
                ReconciliationClass.MATCHED.value
                if all(c == ReconciliationClass.MATCHED.value for c in classifications)
                else "DISCREPANCIES_PRESENT"
            )
        )

        rid = _uid("rec")
        self.store.execute(
            """INSERT INTO br_reconciliations(
                id, provider_snapshot_id, local_snapshot_id, paper_portfolio_ref,
                classifications_json, discrepancies_json, recommendations_json,
                mutated_provider, mutated_portfolio, overall, created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (
                rid, provider_snapshot_id, local_snapshot_id or "",
                str(paper_portfolio.get("id") or ""),
                json.dumps(classifications), json.dumps(discrepancies),
                json.dumps(recommendations),
                0, 0, overall, time.time(),
            ),
        )
        self.store.audit("reconcile.completed", subject=rid, detail={
            "overall": overall, "mutated": False,
        })
        return {
            "id": rid,
            "provider_snapshot_id": provider_snapshot_id,
            "local_snapshot_id": local_snapshot_id or None,
            "classifications": classifications,
            "discrepancies": discrepancies,
            "recommendations": recommendations,
            "mutated_provider": False,
            "mutated_portfolio": False,
            "overall": overall,
            "simulation_only": True,
        }

    def list_results(self) -> list[dict[str, Any]]:
        rows = self.store.fetchall(
            "SELECT * FROM br_reconciliations ORDER BY created_at DESC LIMIT 50"
        )
        out = []
        for r in rows:
            out.append({
                "id": r["id"],
                "provider_snapshot_id": r["provider_snapshot_id"],
                "local_snapshot_id": r["local_snapshot_id"],
                "classifications": json.loads(r["classifications_json"] or "[]"),
                "discrepancies": json.loads(r["discrepancies_json"] or "[]"),
                "recommendations": json.loads(r["recommendations_json"] or "[]"),
                "mutated_provider": bool(r["mutated_provider"]),
                "mutated_portfolio": bool(r["mutated_portfolio"]),
                "overall": r["overall"],
                "created_at": r["created_at"],
            })
        return out


__all__ = [
    "AccountSnapshotService",
    "ReconciliationEngine",
    "SnapshotError",
    "default_fixture_snapshot",
]
