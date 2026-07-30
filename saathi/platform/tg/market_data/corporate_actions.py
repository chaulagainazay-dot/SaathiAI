"""M259 — Corporate actions with provenance. Never destroys raw prices."""
from __future__ import annotations

import json
import time
from typing import Any

from saathi.platform.tg.market_data.models import AUTHORITY_VALUES, CorporateActionType
from saathi.platform.tg.market_data.storage import MarketDataStore, evidence_hash, _uid


class CorporateActionEngine:
    def __init__(self, store: MarketDataStore):
        self.store = store

    def add(
        self,
        dataset_id: str,
        dataset_version: str,
        *,
        symbol: str,
        action_type: str,
        effective_date: str,
        availability_date: str | None = None,
        factor: float = 1.0,
        amount: float | None = None,
        detail: dict | None = None,
        provenance: str = "fixture",
        adjustment_version: str = "v1",
    ) -> dict[str, Any]:
        if action_type not in {t.value for t in CorporateActionType}:
            return {"ok": False, "code": "UNKNOWN_ACTION_TYPE", "action_type": action_type, **AUTHORITY_VALUES}
        rec = {
            "id": _uid("ca"),
            "dataset_id": dataset_id,
            "dataset_version": dataset_version,
            "symbol": symbol.upper(),
            "action_type": action_type,
            "effective_date": effective_date,
            "availability_date": availability_date or effective_date,
            "factor": factor,
            "amount": amount,
            "detail": detail or {},
            "provenance": provenance,
            "adjustment_version": adjustment_version,
        }
        eh = evidence_hash(rec)
        self.store.execute(
            """INSERT INTO md_corporate_actions(
                id, dataset_id, dataset_version, symbol, action_type, effective_date,
                availability_date, factor, amount, detail_json, provenance, adjustment_version, created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                rec["id"], dataset_id, dataset_version, rec["symbol"], action_type,
                effective_date, rec["availability_date"], factor, amount,
                json.dumps(detail or {}), provenance, adjustment_version, time.time(),
            ),
        )
        self.store.audit("corporate_action.add", subject=dataset_id, detail=rec)
        out = {**rec, "evidence_hash": eh, "ok": True, "raw_prices_preserved": True, **AUTHORITY_VALUES}
        return out

    def list(self, dataset_id: str, dataset_version: str) -> dict[str, Any]:
        rows = self.store.query(
            """SELECT * FROM md_corporate_actions WHERE dataset_id=? AND dataset_version=?
               ORDER BY effective_date""",
            (dataset_id, dataset_version),
        )
        actions = []
        for r in rows:
            actions.append({
                "id": r["id"],
                "symbol": r["symbol"],
                "action_type": r["action_type"],
                "effective_date": r["effective_date"],
                "availability_date": r["availability_date"],
                "factor": r["factor"],
                "amount": r["amount"],
                "detail": json.loads(r["detail_json"] or "{}"),
                "provenance": r["provenance"],
                "adjustment_version": r["adjustment_version"],
            })
        return {
            "ok": True,
            "count": len(actions),
            "actions": actions,
            "raw_prices_preserved": True,
            **AUTHORITY_VALUES,
        }
