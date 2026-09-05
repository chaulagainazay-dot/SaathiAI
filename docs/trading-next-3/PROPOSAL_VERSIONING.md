# PROPOSAL_VERSIONING

Version pins:

- portfolio_snapshot_ref (hash of cash/positions/event_count)
- market_price_snapshot_ref
- risk_budget_version

Material ledger change → STALE_PROPOSAL. Supersession via supersedes_proposal_id without mutating history.

