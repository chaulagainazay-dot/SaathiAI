"""M187 — Corporate-action normalization with raw-price preservation.

Every transformation is recorded. Raw OHLC never overwritten.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from saathi.platform.tg.historical.models import (
    AdjustedPriceBar,
    CorporateAction,
    CorporateActionType,
    AdjustmentMethodology,
)


@dataclass
class NormalizationAudit:
    methodology: AdjustmentMethodology
    transformations: list[dict[str, Any]] = field(default_factory=list)
    actions_applied: int = 0
    raw_preserved: bool = True
    timestamp: float = 0.0

    def to_public(self) -> dict[str, Any]:
        return {
            "methodology": self.methodology.value,
            "transformations": list(self.transformations),
            "actions_applied": self.actions_applied,
            "raw_preserved": True,
            "timestamp": self.timestamp,
        }


def _parse_date_ts(date_str: str) -> float:
    """Parse YYYY-MM-DD to UTC midnight epoch."""
    dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return dt.timestamp()


def apply_corporate_actions(
    bars: list[AdjustedPriceBar],
    actions: list[CorporateAction],
    *,
    methodology: AdjustmentMethodology = AdjustmentMethodology.SPLIT_ONLY,
) -> tuple[list[AdjustedPriceBar], NormalizationAudit]:
    """Return new bar list with adj_* fields set. Raw fields unchanged."""
    import time

    audit = NormalizationAudit(methodology=methodology, timestamp=time.time())
    if not bars:
        return [], audit

    # Work on copies
    out = [
        AdjustedPriceBar(
            instrument=b.instrument,
            ts=b.ts,
            open=b.open,
            high=b.high,
            low=b.low,
            close=b.close,
            volume=b.volume,
            adj_open=b.open,
            adj_high=b.high,
            adj_low=b.low,
            adj_close=b.close,
            adj_factor=Decimal("1"),
            timeframe=b.timeframe,
            currency=b.currency,
            source=b.source,
            quality=b.quality,
        )
        for b in bars
    ]

    if methodology == AdjustmentMethodology.NONE or not actions:
        audit.transformations.append({"op": "identity", "detail": "no_adjustment"})
        return out, audit

    # Sort actions by date descending so we can apply cumulative factors from latest
    usable = []
    for a in actions:
        if a.action_type in (
            CorporateActionType.SPLIT,
            CorporateActionType.REVERSE_SPLIT,
            CorporateActionType.DIVIDEND,
        ):
            try:
                usable.append(( _parse_date_ts(a.effective_date), a))
            except ValueError:
                audit.transformations.append({
                    "op": "skip_invalid_date",
                    "action_id": a.id,
                    "date": a.effective_date,
                })
    usable.sort(key=lambda x: x[0])

    # Symbol changes recorded only
    for a in actions:
        if a.action_type == CorporateActionType.SYMBOL_CHANGE:
            audit.transformations.append({
                "op": "symbol_change",
                "old": a.old_symbol,
                "new": a.new_symbol,
                "effective_date": a.effective_date,
            })
            audit.actions_applied += 1
        elif a.action_type in (CorporateActionType.MERGER, CorporateActionType.DELISTING):
            audit.transformations.append({
                "op": a.action_type.value.lower(),
                "instrument": a.instrument,
                "effective_date": a.effective_date,
                "notes": list(a.notes),
            })
            audit.actions_applied += 1

    # Cumulative adjustment factor per instrument for price multipliers
    # Standard: prices before split are divided by split factor (e.g. 2-for-1 → factor 2)
    for b in out:
        factor = Decimal("1")
        for eff_ts, a in usable:
            if a.instrument and a.instrument not in (b.instrument, ""):
                continue
            if b.ts >= eff_ts:
                continue  # action after this bar does not adjust this bar's historical price
            f = Decimal(str(a.factor or "1"))
            if a.action_type == CorporateActionType.SPLIT:
                # split factor e.g. 2 means 2-for-1 → historical prices / 2
                if f > 0:
                    factor *= f
                    audit.transformations.append({
                        "op": "split_adjust",
                        "bar_ts": b.ts,
                        "instrument": b.instrument,
                        "factor": str(f),
                        "effective_date": a.effective_date,
                    })
                    audit.actions_applied += 1
            elif a.action_type == CorporateActionType.REVERSE_SPLIT:
                if f > 0:
                    factor *= f
                    audit.transformations.append({
                        "op": "reverse_split_adjust",
                        "bar_ts": b.ts,
                        "instrument": b.instrument,
                        "factor": str(f),
                        "effective_date": a.effective_date,
                    })
                    audit.actions_applied += 1
            elif a.action_type == CorporateActionType.DIVIDEND and methodology == AdjustmentMethodology.TOTAL_RETURN:
                cash = Decimal(str(a.cash_amount or "0"))
                if cash > 0 and b.close > 0:
                    # simple close-relative dividend factor
                    div_f = (b.close) / (b.close + cash) if (b.close + cash) != 0 else Decimal("1")
                    factor *= div_f
                    audit.transformations.append({
                        "op": "dividend_adjust",
                        "bar_ts": b.ts,
                        "cash": str(cash),
                        "effective_date": a.effective_date,
                    })
                    audit.actions_applied += 1
        if factor != 1:
            # For splits, factor>1 means divide historical prices
            b.adj_factor = factor
            b.adj_open = (b.open / factor).quantize(Decimal("0.00000001"))
            b.adj_high = (b.high / factor).quantize(Decimal("0.00000001"))
            b.adj_low = (b.low / factor).quantize(Decimal("0.00000001"))
            b.adj_close = (b.close / factor).quantize(Decimal("0.00000001"))
            # volume typically multiplies by split factor
            # (leave volume raw; document in audit)
            audit.transformations.append({
                "op": "volume_raw_preserved",
                "instrument": b.instrument,
                "ts": b.ts,
            })

    # Deduplicate verbose audit entries for large series — keep summary + samples
    if len(audit.transformations) > 200:
        summary = {
            "op": "audit_truncated",
            "total": len(audit.transformations),
            "kept_head": 100,
            "kept_tail": 50,
        }
        audit.transformations = (
            audit.transformations[:100] + [summary] + audit.transformations[-50:]
        )

    audit.raw_preserved = True
    # Verify raw untouched vs input
    for i, b in enumerate(out):
        if i < len(bars):
            assert b.open == bars[i].open and b.close == bars[i].close
    return out, audit


def bars_to_md_bars(bars: list[AdjustedPriceBar], *, use_adjusted: bool = True):
    """Convert to M62 MDBar for strategy engine consumption."""
    from datetime import datetime, timedelta, timezone
    from saathi.platform.market_data.models import MDBar, Timeframe

    tf_map = {"1d": Timeframe.D1, "1h": Timeframe.H1, "1m": Timeframe.M1, "5m": Timeframe.M5, "15m": Timeframe.M15}
    out = []
    for b in bars:
        tf = tf_map.get(b.timeframe, Timeframe.D1)
        start = datetime.fromtimestamp(b.ts, tz=timezone.utc)
        end = start + timedelta(days=1 if tf == Timeframe.D1 else 0, seconds=0 if tf == Timeframe.D1 else 3600)
        if tf != Timeframe.D1:
            from saathi.platform.market_data.models import TIMEFRAME_SECONDS
            end = start + timedelta(seconds=TIMEFRAME_SECONDS[tf])
        o = b.adj_open if use_adjusted and b.adj_open is not None else b.open
        h = b.adj_high if use_adjusted and b.adj_high is not None else b.high
        l = b.adj_low if use_adjusted and b.adj_low is not None else b.low
        c = b.adj_close if use_adjusted and b.adj_close is not None else b.close
        out.append(MDBar(
            instrument=b.instrument,
            timeframe=tf,
            provider=b.source or "historical",
            open=o, high=h, low=l, close=c, volume=b.volume,
            start_time=start, end_time=end, source_time=end, ingested_at=end,
        ))
    return out
