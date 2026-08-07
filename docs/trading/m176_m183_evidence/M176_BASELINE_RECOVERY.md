# M176 — Authoritative Baseline Recovery

## Recovery point

| Field | Value |
| --- | --- |
| Branch (pre-work) | `milestone/m166-m175-trading-guardian-foundation` |
| HEAD (verified) | `89fc0b2eae73a4e4a99ffb1a6a65aae2e091632e` |
| Working branch | `milestone/m176-m183-trading-guardian-paper-validation` |
| Private-alpha docs baseline | `2cd61738522ff68968d24e4db56981b42fb8b965` |
| M166–M175 verdict | `TRADING_GUARDIAN_RESEARCH_AND_PAPER_FOUNDATION_READY_WITH_LIMITATIONS` |

## Preserved pre-existing unstaged / untracked (DO NOT MODIFY OR COMMIT)

- `docs/evidence/m25/LATEST_ENVIRONMENT_OBSERVATION.json`
- `docs/evidence/m25/LIVE_CERT_EVIDENCE.json`
- `docs/evidence/m25/LIVE_CERT_SUMMARY.md`
- `docs/evidence/m27/connector_events.jsonl`
- `docs/evidence/m28/deprecation_events.jsonl`
- `docs/design-spec/` (untracked)

## Fixture / synthetic metric entry points (M166–M175)

| Location | Risk | M176–M183 action |
| --- | --- | --- |
| `tg/service.py` `run_backtest` except-path → `COMPLETE_WITH_FIXTURE_METRICS` with fabricated metrics | **Critical** — silent authoritative pollution | Fail closed: `INCOMPLETE` / `REJECTED`; never substitute fake metrics |
| M62 `market_data.fixtures.build_bars` used as research dataset | Synthetic validation only | Label `SYNTHETIC_VALIDATION` or `FIXTURE_TEST_ONLY` |
| Strategy compare without data classification | Misleading | Require classification on every scorecard |
| Browser cert M166–M175 | Static/label only | Full Playwright localhost walkthrough |

## Browser routes not live-walkthrough certified (M166–M175)

`/trading`, `/trading/accounts`, `/trading/orders`, `/trading/positions`,
`/trading/strategies`, `/trading/regime`, `/trading/proposals`,
`/trading/backtests`, `/trading/comparison`, `/trading/journal`,
`/trading/policy`, `/trading/reconciliation`, `/trading/safety`,
`/trading/approvals`, `/trading/evidence`

## Non-negotiable policy

`AUTHORITATIVE_RESULT_REQUIRES_NON_FIXTURE_DATA` — enforced in M177+.
