# IDEMPOTENT_RETRY

- Key: `fill:{fill_id}`
- Duplicate post → status DUPLICATE / POSTED, no double cash
- Crash after OMS before post → restart + `retry_ledger_posts`
- Duplicate market event → OMS no-op + pending retry

