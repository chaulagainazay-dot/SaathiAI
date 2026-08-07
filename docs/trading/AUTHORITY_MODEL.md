# Trading Authority Model

Canonical chain (unchanged by M62):
```
Operator → SaathiOS UI/API → Platform services → PlatformAgentRuntime
→ ExecutionGateway → Registered trading/research tool → Approved external provider
```

- PlatformAgentRuntime remains the canonical agent runtime.
- ExecutionGateway remains the sole authority for registered-tool execution.
- Approvals are server-owned, tenant-scoped, expiring, single/bounded-use.
- Trading Guardian (`trading_guardian.py`) holds FINAL VETO before any order intent
  may proceed; it is independent of strategy/research agents and fail-closed.
- Agents may research, analyze, backtest, simulate, and PROPOSE order intents. They
  may not bypass approval, risk, runtime, gateway, provider, reconciliation, or audit.

## Disabled in M62 (fail-closed)
LEVERAGE · MARGIN · SHORT_SELLING · OPTIONS · FUTURES · PERPETUALS · DERIVATIVES ·
BORROWING · AUTONOMOUS_LIVE_EXECUTION · LIVE order environment. The Guardian refuses
to construct with any of these enabled; `Environment.LIVE` is always vetoed.

Highest permitted target: PAPER_TRADING (not yet reached — see INTAKE_AUDIT plan).
