# Quality

Canonical quality is `VALID` only after schema, venue, symbol, timestamp, positive-price and OHLC checks. Lifecycle degradation is explicit (`DISCONNECTED`, `GAPPED`, `INVALID` in the stream controller). Crypto has no weekend closure inference; provider silence is not market closure.
