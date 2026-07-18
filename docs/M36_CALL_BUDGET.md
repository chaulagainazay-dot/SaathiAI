# M36 — Call Budget

```
max total calls = 3
```

Preferred allocation:

1. Authenticated identity (`GET /user`)
2. Approved operation (`GET /meta`)
3. Optional repeatability / bounded retry

Retries, redirects (as new requests), and auth retries **consume** budget.
Fourth call fails closed.

No hidden telemetry, SDK discovery, pagination, OAuth refresh, silent retry, or
alternate-host fallback.
