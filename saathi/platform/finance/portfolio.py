"""Read-only portfolio contracts (pure). Never canonical market data, never md_bars/
md_quotes, zero execution authority. No fabricated fields — missing stays None.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from enum import Enum


class PortfolioSourceType(str, Enum):
    OWNER_AUTHENTICATED_BROWSER_OBSERVED = "OWNER_AUTHENTICATED_BROWSER_OBSERVED"
    READ_ONLY_API_ACCOUNT_DATA = "READ_ONLY_API_ACCOUNT_DATA"
    READ_ONLY_MCP_ACCOUNT_DATA = "READ_ONLY_MCP_ACCOUNT_DATA"
    OWNER_IMPORTED_PORTFOLIO = "OWNER_IMPORTED_PORTFOLIO"


class PortfolioFreshness(str, Enum):
    FRESH = "FRESH"
    STALE = "STALE"
    UNAVAILABLE = "UNAVAILABLE"


def dec(v) -> Decimal | None:
    if v is None:
        return None
    t = str(v).strip().replace(",", "")
    if t in ("", "-", "--", "N/A", "null", "None"):
        return None
    try:
        return Decimal(t)
    except (InvalidOperation, ValueError):
        return None


@dataclass(frozen=True)
class Position:
    instrument_id: str
    symbol: str
    asset_type: str                      # EQUITY / CRYPTO / STABLECOIN / CASH
    quantity: Decimal | None = None
    available_quantity: Decimal | None = None
    locked_quantity: Decimal | None = None
    average_cost: Decimal | None = None
    current_price: Decimal | None = None
    current_price_source: str = ""       # OFFICIAL_PAGE_OBSERVED / BINANCE_PUBLIC / ...
    market_value: Decimal | None = None
    cost_basis: Decimal | None = None
    unrealized_pnl: Decimal | None = None
    realized_pnl: Decimal | None = None
    currency: str = ""
    source: str = ""
    observed_at: float = 0.0

    def to_public(self) -> dict:
        def s(v):
            return None if v is None else str(v)
        return {k: (s(getattr(self, k)) if isinstance(getattr(self, k), Decimal) else getattr(self, k))
                for k in ("instrument_id", "symbol", "asset_type", "quantity",
                          "available_quantity", "locked_quantity", "average_cost",
                          "current_price", "current_price_source", "market_value",
                          "cost_basis", "unrealized_pnl", "realized_pnl", "currency",
                          "source", "observed_at")}


@dataclass(frozen=True)
class PortfolioSnapshot:
    snapshot_id: str
    owner_id: str
    provider: str
    account_type: str                    # SPOT / NEPSE_DEMAT / ...
    observed_at: float
    currency: str
    source_type: PortfolioSourceType
    data_class: str = "READ_ONLY_PORTFOLIO_OBSERVATION"
    source_authority: str = "OWNER_ACCOUNT_PROVIDER"
    source_timestamp: str = ""
    freshness: PortfolioFreshness = PortfolioFreshness.FRESH
    positions: tuple[Position, ...] = ()
    cash: Decimal | None = None
    total_market_value: Decimal | None = None
    limitations: tuple[str, ...] = ()

    def to_public(self) -> dict:
        def s(v):
            return None if v is None else str(v)
        return {"snapshot_id": self.snapshot_id, "owner_id": self.owner_id,
                "provider": self.provider, "account_type": self.account_type,
                "observed_at": self.observed_at, "currency": self.currency,
                "source_type": self.source_type.value, "data_class": self.data_class,
                "source_authority": self.source_authority, "source_timestamp": self.source_timestamp,
                "freshness": self.freshness.value, "cash": s(self.cash),
                "total_market_value": s(self.total_market_value),
                "positions": [p.to_public() for p in self.positions],
                "note": "read-only observation; NOT canonical market data; no trade authority",
                "limitations": list(self.limitations)}


@dataclass(frozen=True)
class FXObservation:
    pair: str                            # e.g. USDNPR
    rate: Decimal
    source: str
    observed_at: float
    freshness: str = "FRESH"

    def to_public(self) -> dict:
        return {"pair": self.pair, "rate": str(self.rate), "source": self.source,
                "observed_at": self.observed_at, "freshness": self.freshness}


# ── descriptive analytics (deterministic, no recommendation) ────────────────────
def _sum(vals):
    tot = Decimal(0)
    seen = False
    for v in vals:
        if v is not None:
            tot += v
            seen = True
    return tot if seen else None


def snapshot_metrics(snap: PortfolioSnapshot) -> dict:
    """Allocation, concentration, unrealized P/L within ONE currency snapshot."""
    mv = [(p.symbol, p.market_value) for p in snap.positions if p.market_value is not None]
    total = _sum([v for _, v in mv]) or Decimal(0)
    alloc = [{"symbol": sym, "market_value": str(v),
              "weight_pct": (str((v / total * 100).quantize(Decimal("0.01"))) if total else None)}
             for sym, v in sorted(mv, key=lambda x: x[1], reverse=True)]
    upnl = _sum([p.unrealized_pnl for p in snap.positions])
    largest = alloc[0] if alloc else None
    concentration = alloc[0]["weight_pct"] if alloc else None
    return {"currency": snap.currency, "total_market_value": str(total) if total else None,
            "positions": len(snap.positions), "allocation": alloc,
            "largest_position": largest, "top_concentration_pct": concentration,
            "unrealized_pnl": str(upnl) if upnl is not None else None,
            "note": "descriptive analytics only; not investment advice"}


@dataclass(frozen=True)
class UnifiedPortfolioView:
    """Multi-provider view. Currencies are kept SEPARATE — NPR and USD are never summed
    without an explicit sourced FX observation."""
    generated_at: float
    snapshots: tuple[PortfolioSnapshot, ...] = ()
    fx: FXObservation | None = None
    limitations: tuple[str, ...] = ()

    def to_public(self) -> dict:
        by_ccy: dict[str, list] = {}
        for snap in self.snapshots:
            by_ccy.setdefault(snap.currency or "UNKNOWN", []).append(snap)
        buckets = {}
        for ccy, snaps in by_ccy.items():
            tot = _sum([s.total_market_value for s in snaps])
            buckets[ccy] = {"total_market_value": str(tot) if tot is not None else None,
                            "providers": [s.provider for s in snaps],
                            "metrics": [snapshot_metrics(s) for s in snaps]}
        out = {"generated_at": self.generated_at, "by_currency": buckets,
               "fx": self.fx.to_public() if self.fx else None,
               "combined_valuation": None,
               "note": "per-currency totals; no cross-currency sum without sourced FX",
               "limitations": list(self.limitations)}
        # combined valuation ONLY if a sourced FX rate is present (else stays None)
        if self.fx is not None and len(buckets) > 1:
            out["combined_valuation_note"] = (
                f"combined valuation requires converting via {self.fx.pair}="
                f"{self.fx.rate} ({self.fx.source}); provided as explicit sourced conversion")
        return out
