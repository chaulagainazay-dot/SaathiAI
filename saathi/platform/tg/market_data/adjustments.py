"""Price adjustments — always keep raw open/high/low/close intact."""
from __future__ import annotations

from typing import Any

from saathi.platform.tg.market_data.models import AUTHORITY_VALUES
from saathi.platform.tg.market_data.storage import MarketDataStore


class AdjustmentEngine:
    def __init__(self, store: MarketDataStore):
        self.store = store

    def apply_split_adjustments(
        self,
        dataset_id: str,
        dataset_version: str,
        *,
        symbol: str,
        adjustment_version: str = "v1",
    ) -> dict[str, Any]:
        """Compute adjusted_close from corporate actions without mutating raw OHLC."""
        actions = self.store.query(
            """SELECT * FROM md_corporate_actions
               WHERE dataset_id=? AND dataset_version=? AND symbol=?
               AND action_type IN ('stock_split','reverse_split')
               ORDER BY effective_date DESC""",
            (dataset_id, dataset_version, symbol.upper()),
        )
        bars = self.store.query(
            """SELECT id, timestamp, open, high, low, close, adjusted_close
               FROM md_bars WHERE dataset_id=? AND dataset_version=? AND symbol=?
               ORDER BY timestamp""",
            (dataset_id, dataset_version, symbol.upper()),
        )
        if not bars:
            return {"ok": False, "code": "NO_BARS", **AUTHORITY_VALUES}

        # Cumulative factor: for each bar, product of split factors with effective_date > bar date
        updates = 0
        for b in bars:
            factor = 1.0
            for a in actions:
                if a["effective_date"] > b["timestamp"][:10]:
                    # split already happened after this bar → adjust historical down
                    factor *= float(a["factor"] or 1.0)
            adj = float(b["close"]) / factor if factor else float(b["close"])
            # Only update adjusted_close — never raw
            self.store.execute(
                "UPDATE md_bars SET adjusted_close=? WHERE id=?",
                (round(adj, 8), b["id"]),
            )
            updates += 1

        return {
            "ok": True,
            "symbol": symbol.upper(),
            "bars_updated": updates,
            "actions_applied": len(actions),
            "adjustment_version": adjustment_version,
            "raw_prices_preserved": True,
            "raw_fields_untouched": ["open", "high", "low", "close", "volume"],
            "adjusted_field": "adjusted_close",
            **AUTHORITY_VALUES,
        }

    def raw_vs_adjusted(self, dataset_id: str, dataset_version: str, symbol: str, limit: int = 5) -> dict[str, Any]:
        rows = self.store.query(
            """SELECT timestamp, open, high, low, close, adjusted_close, volume
               FROM md_bars WHERE dataset_id=? AND dataset_version=? AND symbol=?
               ORDER BY timestamp LIMIT ?""",
            (dataset_id, dataset_version, symbol.upper(), limit),
        )
        return {
            "ok": True,
            "symbol": symbol.upper(),
            "samples": [dict(r) for r in rows],
            "raw_prices_preserved": True,
            **AUTHORITY_VALUES,
        }
