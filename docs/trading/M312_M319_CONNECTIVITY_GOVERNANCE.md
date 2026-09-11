# M312–M319 — Trading Connectivity Governance

## Terminal Verdict

`TRADING_CONNECTIVITY_GOVERNANCE_CERTIFIED_WITH_LIMITATIONS`

## Maximum State

`CONNECTIVITY_GOVERNANCE_READY_NO_PROVIDER_CONNECTION`

## Current Maturity

`GOVERNANCE_ONLY`

## Package

`saathi/platform/tg/connectivity_governance/`

## Surfaces

- API: `/api/v1/platform/tg/connectivity-governance/*`
- CLI: `cg-verdict`, `cg-charter-show`, `cg-authority-list`, `cg-provider-list`, `cg-certify`
- UI: `/trading/connectivity-governance`

## Invariants

- approval_does_not_equal_activation=true
- authority_does_not_implicitly_expand=true
- raw_credentials_forbidden=true
- deny_overrides_allow=true
- Emergency shutdown dominates all authority
- All connectivity authority values remain false

## Explicit Non-Actions

No provider connection, broker login, OAuth, real credentials, account/balance/position access, orders, canary activation, live trading, or M320 start.

## Recommended Next Milestone

Provider mock-contract work only after separate human authorization (not started).

## Evidence

`docs/trading/m312_m319_evidence/`
