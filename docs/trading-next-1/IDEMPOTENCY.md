# IDEMPOTENCY

- Unique `(fund_id, idempotency_key)` in `fl_events`
- Re-delivery returns `status=duplicate` with prior event; state unchanged
- Tests: S7 duplicate fill, paper bridge double-post

