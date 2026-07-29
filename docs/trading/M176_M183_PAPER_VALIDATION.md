# M176–M183 — Trading Guardian Paper Validation & Operator Certification

**Terminal verdict:** `TRADING_GUARDIAN_PAPER_VALIDATION_CERTIFIED_WITH_LIMITATIONS`

**Date:** 2026-07-29

## Authority

| Claim | Status |
| --- | --- |
| Paper only | YES |
| Live trading authorized | NO |
| Broker credentials | NO |
| Production authorized | NO |
| Profitability claim | NO |
| Owner sign-off | Automated browser only — not human owner sign-off |

## Hard policy

`AUTHORITATIVE_RESULT_REQUIRES_NON_FIXTURE_DATA`

- Fixture metrics never silently replace failed historical runs.
- Failed mappings return `INCOMPLETE` / `REJECTED` with `metrics: null`.
- M62 datasets are labeled `SYNTHETIC_VALIDATION` or `FIXTURE_TEST_ONLY`.
- `PAPER_ELIGIBLE` requires authoritative non-fixture evidence + walk-forward + stress + checklist.

## Modules added

| Module | Role |
| --- | --- |
| `tg/data_contract.py` | Data classification + provenance |
| `tg/walk_forward.py` | Anchored/expanding/rolling WF over M62 folds |
| `tg/stress_lab.py` | Cost/market/data/parameter stress |
| `tg/portfolio.py` | Portfolio risk + scenarios + unreconciled block |
| `tg/recovery.py` | Failure/recovery certification suite |

## API additions

- `POST /tg/walk-forward`
- `POST /tg/stress`
- `GET /tg/scorecard/{slug}`
- `GET /tg/recovery/cert`
- `GET /tg/portfolio/analysis`
- `POST /tg/portfolio/scenario`

## UI

- `/trading/research` — walk-forward, stress, scorecard
- Backtest Lab shows data classification, authoritative flag, fee/slip assumptions

## Disclaimers (mandatory)

- All money is simulated.
- No live order capability.
- No broker credentials supported.
- Historical results do not predict future results.
- Synthetic and fixture results are not market evidence.
- Simulated fills differ from live fills.
- Operator approval does not eliminate financial risk.
