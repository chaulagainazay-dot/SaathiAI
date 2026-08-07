# M48.2 — Capability Resolution

## Canonical names (M48.1 KNOWN_CAPABILITIES)

`plan`, `research`, `code`, `review`, `write`, `architect`, `execute_local`, `chat`, `memory_read`, `memory_write_local`, `diagnostics`, `ceo_brief`, `financial_advisory`, plus prohibited names for deny lists.

## Aliases (`service.CAPABILITY_ALIASES`)

| alias | canonical |
|---|---|
| planning, planner | plan |
| coding, implement, build | code |
| reviewing | review |
| writing, docs | write |
| researching | research |
| ceo, brief | ceo_brief |
| trade, execute_trade | trade_execute (prohibited) |

## Strategy → capability

| strategy | default capability |
|---|---|
| build | code |
| architect_build | architect |
| document | write |
| business | ceo_brief |
| broad_research | research |
| single / default | plan |

Unknown capability → **fail closed** (no generic agent fallback).
