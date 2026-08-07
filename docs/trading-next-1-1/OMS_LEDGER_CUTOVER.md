# OMS_LEDGER_CUTOVER

1. `create_account` opens `fund_{account_id}` with opening deposit.
2. `process_market_event` after successful `persist_fill` calls `_post_fill_to_canonical_ledger`.
3. Posting is idempotent via `fill:{fill_id}`.
4. Reads: `get_account`, `list_positions`, `command_center_snapshot` use ledger.
5. OMS tables retained for orders/fills/reservations.

