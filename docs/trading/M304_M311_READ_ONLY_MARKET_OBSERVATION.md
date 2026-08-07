# M304–M311 — Read-Only Market Observation

## Verdict
`READ_ONLY_MARKET_OBSERVATION_CERTIFIED_WITH_LIMITATIONS`

## Max state
`READ_ONLY_MARKET_OBSERVATION_ONLY`

## Package
`saathi/platform/tg/market_observation/`

## Capabilities
Read-only market snapshots · quotes · historical refresh · symbol metadata ·
exchange status · corporate actions · benchmark updates.

## Forbidden
Broker login · OAuth · trading · orders · portfolio access · account balances ·
API credential storage · order execution · authenticated live feeds.

## Surfaces
- API: `/api/v1/platform/tg/market-observation/*`
- CLI: `mo-*` / `paper-gov mo-*`
- UI: `/trading/market-observation`

## Purpose
**Validation — not trading.** Offline fixtures by default.

## Master roadmap
Phases 1–4 of the post-M272–M279 master roadmap are complete under
paper/research/read-only authority. Live broker connectivity remains a
separate future governance programme.
