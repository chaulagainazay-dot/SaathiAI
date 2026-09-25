# LEGACY_STORE_BOUNDARY

```text
LEGACY_OMS_STATE_NOT_BOOKS_AUTHORITY
```

OMS may store:

- order lifecycle
- fill production history
- reserved cash/qty
- avg-cost **shadow** for compatibility

OMS must **not** be used as authoritative:

- NAV, cash books, portfolio P&L, exposure, canonical positions

