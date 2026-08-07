# M288–M295 — Institutional Paper Trading Simulation

## Verdict
`INSTITUTIONAL_PAPER_TRADING_SIMULATION_CERTIFIED_WITH_LIMITATIONS`

## Max state
`INSTITUTIONAL_PAPER_SIMULATION_ONLY`

## Package
`saathi/platform/tg/paper_simulation/`

## Capabilities
Virtual exchange · matching engine · order book · market/limit/stop orders ·
partial fills · slippage · liquidity · latency · sessions · portfolio/cash ledger ·
positions · research margin (capped) · corporate actions · dividends · trading calendar ·
trade journal · fill audit · risk monitor · kill switch · dashboard.

## Surfaces
- API: `/api/v1/platform/tg/paper-simulation/*`
- CLI: `ps-*` / `paper-gov ps-*`
- UI: `/trading/paper-simulation`

## Authority
**No broker. No API keys. No real exchange account. No live trading.**
Paper orders exist only inside the virtual exchange.

## Next
Phase 3 M296–M303 Institutional Portfolio & Risk Intelligence (still no broker).
