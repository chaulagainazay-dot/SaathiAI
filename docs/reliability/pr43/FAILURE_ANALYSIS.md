# FAILURE_ANALYSIS — PR #43 reliability

## Source

- Branch: `feature/t-next-4-performance-attribution`
- Base SHA: `b05907b3aad437f225ad98200c037daddaf600ba`
- Reliability run (reported): critical-regressions PASS; full-suite FAIL (7381 passed, 2 failed)

## Failures

| Test | Symptom |
| --- | --- |
| `tests/test_m17_1_live.py::test_live_browser_dom_and_click` | `query_exists("#submit")` False after title contains "Pilot" |
| `tests/test_m62_8_workspace.py::test_account_detail_exposes_halt_reason` | `mark_source` expected `replay/fixture`, got `canonical_fund_ledger_marks_or_cost` |

## T-NEXT-4 relation

Neither failure originates in PortfolioPerformanceEngine, performance API, or Command `paper_performance`. Both pre-exist as harness/stale-contract issues relative to T-NEXT-1.1 ledger cutover and LiveBrowserDriver CDP readiness.
