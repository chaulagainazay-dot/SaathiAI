# PROPOSAL_SCHEMA

Immutable `PortfolioProposal` fields (minimum):

proposal_id, created_at, fund_id, portfolio_snapshot_ref, risk_budget_version, method/source,
target_allocations, trades, projected_cash, projected_nav, projected_exposure, projected_risk,
current/proposed/delta summaries, rationale (reason_codes), warnings, status, valid_until,
market_price_snapshot_ref, supersedes_proposal_id, authorizes_execution=false, mode=PAPER.

