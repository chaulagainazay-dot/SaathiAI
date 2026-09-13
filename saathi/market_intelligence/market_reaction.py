"""Phase 2/5 — point-in-time-safe MARKET_REACTION (descriptive history only).

NOT expected return / forecast / signal strength. Look-ahead prevention is the
core invariant: 'price_after' is the FIRST bar that became available STRICTLY
after the event publication; 'price_before' is the LAST bar available at/before
it. A bar available at/before publication can NEVER be used as the 'after' price.
Canonical structured market data owns numeric prices; browser/research evidence
never overrides them. The bar reader is injected; absence → typed degraded.
"""
from __future__ import annotations

from saathi.market_intelligence.catalyst import MarketContext, MarketContextStatus

# A bar reader returns, for a NEPSE symbol, a list of dicts sorted by availability:
#   {"available_at": float(unix), "close": str, "volume": str, "session_date": str}
# from the CANONICAL market-data store (MD-1 available_at semantics). No live NEPSE
# feed exists yet → the default reader returns [] → MARKET_DATA_UNAVAILABLE.


def _num(x) -> float | None:
    try:
        return float(str(x).replace(",", ""))
    except (TypeError, ValueError):
        return None


def compute_market_reaction(symbol: str, publication_ts: float | None, *, reader,
                            window: str = "prev_close->first_close_after_pub") -> MarketContext:
    if not symbol:
        return MarketContext(MarketContextStatus.SYMBOL_UNRESOLVED, window=window,
                             detail="no resolved symbol")
    if publication_ts is None:
        return MarketContext(MarketContextStatus.TIMESTAMP_UNRESOLVED, window=window,
                             detail="publication timestamp unresolved")
    if reader is None:
        return MarketContext(MarketContextStatus.MARKET_DATA_UNAVAILABLE, window=window,
                             detail="no canonical market-data reader")
    try:
        bars = list(reader(symbol) or [])
    except Exception as e:
        return MarketContext(MarketContextStatus.MARKET_DATA_UNAVAILABLE, window=window,
                             detail=f"reader error: {type(e).__name__}")
    if not bars:
        return MarketContext(MarketContextStatus.MARKET_DATA_UNAVAILABLE, window=window,
                             detail="no canonical bars for symbol")

    bars = sorted(bars, key=lambda b: float(b.get("available_at", 0.0)))
    before = [b for b in bars if float(b.get("available_at", 0.0)) <= publication_ts]
    after = [b for b in bars if float(b.get("available_at", 0.0)) > publication_ts]  # STRICTLY after
    if not before or not after:
        return MarketContext(MarketContextStatus.INSUFFICIENT_HISTORY, window=window,
                             detail=f"before={len(before)} after={len(after)} around publication",
                             sessions_used=0)

    b0, a0 = before[-1], after[0]
    pc, ac = _num(b0.get("close")), _num(a0.get("close"))
    vb, va = _num(b0.get("volume")), _num(a0.get("volume"))
    abs_change = pct_change = vol_ratio = ""
    if pc is not None and ac is not None:
        abs_change = f"{ac - pc:.4f}"
        if pc != 0:
            pct_change = f"{(ac - pc) / pc * 100:.2f}%"
    if vb not in (None, 0) and va is not None:
        vol_ratio = f"{va / vb:.3f}"
    return MarketContext(
        MarketContextStatus.OK, window=window,
        price_before=str(b0.get("close", "")), price_after=str(a0.get("close", "")),
        absolute_change=abs_change, percentage_change=pct_change,
        volume_before=str(b0.get("volume", "")), volume_after=str(a0.get("volume", "")),
        volume_ratio=vol_ratio, sessions_used=1,
        detail=f"before_session={b0.get('session_date','')} after_session={a0.get('session_date','')}")
