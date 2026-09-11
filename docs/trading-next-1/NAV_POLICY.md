# NAV_POLICY

```text
NAV = cash + market_value(open lots)
market_value = qty × mark_price
```

- Mark includes `ts`, `source`, `max_age_seconds`
- Stale marks still compute value but flag `mark_stale=true` (never pretend fresh)
- Missing mark → use cost (unrealized ≈ 0)
- Valuation snapshots stored optionally; **ledger events remain authority**

