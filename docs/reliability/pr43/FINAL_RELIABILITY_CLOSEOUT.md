# FINAL_RELIABILITY_CLOSEOUT — PR #43

## Verdict (local full suite)

```text
PR43_RELIABILITY_FULLY_GREEN
```

(Subject to matching GitHub reliability: critical-regressions PASS + full-suite PASS.)

## Fixes

1. **DOM readiness race** — `LiveBrowserDriver.wait_dom_ready` / `wait_for_selector` (bounded 5s).
2. **Stale mark_source expectation** — post T-NEXT-1.1 books authority; test + explicit cutover contract test.

## Authority

ZERO_AUTHORITY_CHANGE for EG, TG, ledger/risk/proposal/performance product authority, live trading, approvals, voice.

## Non-actions

- No merge of PR #42 or #43
- No UI-NEXT-3.1
