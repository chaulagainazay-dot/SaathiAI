# LOT_ACCOUNTING

FIFO open lots:

```text
lot_id = lot_{fill_ref|event_id}   # stable across replay
quantity_open / quantity_original
cost_price (includes allocated buy fee)
fill_ref, opened_ts, currency
```

SELL consumes oldest open lots first. Oversell → error (no short).
Position quantity = sum(open lots). Realized P&L from closed lot slices only.

