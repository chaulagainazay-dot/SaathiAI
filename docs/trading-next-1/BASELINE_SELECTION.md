# BASELINE_SELECTION — T-NEXT-1

## Selected base

| Field | Value |
| --- | --- |
| Branch base | `feature/ui-next-1-central-command` |
| Base SHA | `d66fa3aea03dbb8f5daed431ff62d64fad7906a9` |
| Work branch | `feature/t-next-1-canonical-paper-ledger` |
| Worktree | `~/SaathiAI-trading-next-1` |

## Why this base

1. **Contains trading stack ancestry** through M192–M303 paper / portfolio / TG (also present on `integration/saathios-canonical-baseline`).
2. **Contains UI-NEXT-1 Central Command** composition — required for Command Center investment metrics (Phase 27–28).
3. **Is a descendant of** `integration/saathios-canonical-baseline` (`2030257`) — verified via merge-base.
4. **Does not include** voice data-collection branch `data/v-next-2b6-product-clean-speech` / PR #34 — speech campaign remains independent.

## Explicitly not chosen

| Candidate | Reason |
| --- | --- |
| `data/v-next-2b6-product-clean-speech` | Human-data collection only; would pollute trading with speech tooling |
| `master` | Missing M200/M288/M296 paper stack |
| `integration/saathios-canonical-baseline` alone | Missing Central Command UI composition |
| Voice milestone tips | Unrelated to portfolio authority |

## Voice track (untouched)

```text
PR #34
data/v-next-2b6-product-clean-speech
V-NEXT-2B.7 blocked until training authorization gate passes
```

