# Live-Readiness Blockers (and Paper-Readiness gaps)

LIVE real-capital trading is NOT authorized and is out of scope for M62.
Even PAPER_TRADING_READY is NOT yet reached. Outstanding before paper-ready:

- Market-data quality layer + deterministic replay (M62.2) — MISSING
- Evidence-graded research pipeline, platform-integrated (M62.3) — MISSING
- Deterministic backtesting with bias/leakage protections (M62.4) — MISSING
- Trading Guardian persistence + portfolio-risk wiring (M62.5) — pure logic only
- Approval-bound order-intent persistence + state-machine wiring (M62.6) — models only
- Deterministic in-process paper broker (M62.7) — MISSING
- Reconciliation, recovery, durable circuit breakers (M62.8) — MISSING
- Agentic scheduling + monitoring (M62.9) — MISSING
- Operator UI integration (M62.10) — MISSING (only advisory BlockedState)
- Adversarial security certification (M62.11) — MISSING
- End-to-end paper-trading browser certification (M62.12) — MISSING

Additional live-only blockers (future authorized milestone): external sandbox/broker
credentials, legal agreements, market-data subscriptions, real-capital authorization.
