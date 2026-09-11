# BASELINE_SELECTION — UI-NEXT-2

## Selected base

| Field | Value |
| --- | --- |
| Branch base | `feature/ui-next-1-central-command` |
| Base SHA | `d66fa3aea03dbb8f5daed431ff62d64fad7906a9` |
| Work branch | `design/ui-next-2-saathios-design-dna` |
| Worktree | `~/SaathiAI-ui-next-2` |

## Why

1. Owns Central Command composition (`/command`, command components, composition libs).
2. Verified UI-NEXT-1 certification tip.
3. Does **not** pull speech-data PR #34.
4. Does **not** merge trading PRs #35–#37 into the design branch.

## T-NEXT contract consumption (without merge)

Design prototypes use **representative field names** from:

- T-NEXT-1 ledger: `paper_nav`, `cash`, `realized_pnl`, `unrealized_pnl`, `gross_exposure`, `net_exposure`, `positions`, `reconciliation`
- T-NEXT-1.1: `books_authority`, `portfolio_status`, `RECONCILIATION_REQUIRED`
- T-NEXT-2: `risk_status`, `drawdown`, `risk_budget_consumed`, `stress_loss`, `reason_codes`, `PAPER RISK`

All demo values labeled **DEMO / MOCK**.

## Explicit non-bases

| Candidate | Why rejected |
| --- | --- |
| `data/v-next-2b6-product-clean-speech` | Human speech data track |
| `feature/t-next-2-*` alone | Trading implementation, not UI ancestry |

