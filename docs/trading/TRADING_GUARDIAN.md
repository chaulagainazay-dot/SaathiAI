# Trading Guardian

`saathi/platform/trading_guardian.py` — independent, fail-closed risk-veto engine
with final veto before an order intent may proceed. Pure logic (no network, no
execution). 19 unit tests (`tests/test_m62_trading_models.py`).

## Construction fail-closed
Refuses to construct if any of LEVERAGE/MARGIN/SHORT_SELLING/OPTIONS/FUTURES/
PERPETUALS/DERIVATIVES/BORROWING/AUTONOMOUS_LIVE_EXECUTION is enabled.

## Evaluate() checks (all must pass; any failure → veto with reason)
Circuit armed · environment non-live (LIVE always vetoed; unknown vetoed) ·
no short-selling (SELL ≤ held) · price quality VALID · market OPEN · quantity>0 ·
idempotency key present · approval present · limit price present for LIMIT ·
price-deviation ≤ limit · order notional ≤ max · buying power (BUY) ·
position notional ≤ max · concentration ≤ max% · gross exposure ≤ max ·
open positions ≤ max · symbol not restricted.

## Circuit breaker
`trip(reason)` → `CircuitState.TRIPPED` fail-closed; `reset()` re-arms. (Durable
persistence across restarts is M62.8.)

## Limitations (this milestone)
Guardian is pure logic, not yet persisted or wired into an order pipeline (no
pipeline exists yet). Account/market inputs are passed in by the caller; there is
no live market-data feed or paper broker yet (M62.2, M62.7).
