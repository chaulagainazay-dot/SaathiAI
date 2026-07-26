# M62.2 — Data Quality

Detailed `MarketDataQuality`: VALID, STALE, INCOMPLETE, OUTLIER, GAPPED, DUPLICATE,
OUT_OF_ORDER, UNVERIFIED, MARKET_CLOSED, PROVIDER_ERROR, INVALID_TIMESTAMP,
INVALID_PRICE — plus structured `QualityFinding`s. Maps down to the coarse
`DataQuality` the Trading Guardian consumes; only VALID is tradeable, so any defect
fails the Guardian's `price_quality_valid` check closed.

## Quote checks
naive/future timestamp → INVALID_TIMESTAMP; missing field → INCOMPLETE; non-positive
or crossed (bid>ask) → INVALID_PRICE; spread > 10% of mid → OUTLIER; market closed →
MARKET_CLOSED; age > freshness → STALE.

## Bar checks
naive/future timestamp, non-positive/mismatched duration → INVALID_TIMESTAMP/INCOMPLETE;
missing OHLC → INCOMPLETE; negative / high<low / open|close outside [low,high] →
INVALID_PRICE; close move > 50% vs prev → OUTLIER. Series-level: DUPLICATE_INTERVAL,
OUT_OF_ORDER, GAP_BEFORE (missing intervals).

Rejection policy: rejected records never enter the valid dataset; their metadata +
content hash are retained in `md_rejects` for evidence only.
