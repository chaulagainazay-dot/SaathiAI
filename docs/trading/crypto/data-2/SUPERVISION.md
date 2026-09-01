# CRYPTO-DATA-2 supervision

`MarketDataSupervisor` provides explicit liveness (`CONNECTED`, `LIVE`, `STALE`, `BACKOFF`, `FAILED`), bounded exponential reconnect accounting, and bounded capture. Liveness is based on valid observed events, not socket presence. Crypto is treated as 24/7; silence is stale/degraded, never market closure.
