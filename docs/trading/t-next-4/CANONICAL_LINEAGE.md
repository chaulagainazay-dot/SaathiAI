# T-NEXT-4 — Canonical Trading Lineage

## The finding

The trading work is a **stacked PR chain**, not a set of parallel branches, and
it is rooted off `feature/ui-next-1-central-command` — not off the branch that
recent non-trading work has been landing on.

Verified with `git merge-base --is-ancestor`, not from documentation:

```
feature/ui-next-1-central-command
  └─ feature/t-next-1-canonical-paper-ledger          PR #35
       └─ feature/t-next-1-1-paper-ledger-cutover     PR #36
            └─ feature/t-next-2-independent-risk-engine    PR #37
                 └─ feature/t-next-3-portfolio-construction PR #41
                      └─ feature/t-next-4-performance-attribution PR #43
                           └─ integration/saathios-trunk-v3   PR #45
```

Every link above is **LINEAR** (each is an ancestor of the next). There is no
divergence to reconcile inside the chain.

## Position of `milestone/m312-m319-connectivity-governance`

This is where the ECC hardening and the TradingAgents evaluation were committed.
Measured against the chain:

| Branch | ahead of m312-m319 | behind m312-m319 |
|---|---|---|
| `feature/t-next-1-canonical-paper-ledger` | 140 | 2 |
| `feature/t-next-3-portfolio-construction` | 155 | 2 |
| `feature/t-next-4-performance-attribution` | 181 | 2 |
| `integration/saathios-trunk-v3` | **251** | 2 |

The "2 behind" in every row is exactly the two documentation commits from the
previous missions. **`milestone/m312-m319` is not the trading trunk** — it is 251
commits behind it and does not contain `saathi/platform/fund_ledger/` or
`saathi/platform/portfolio_construction/` at all.

Building execution integrity there would have meant building against a tree with
no canonical ledger and no construction engine.

## Name collision worth recording

PR #43 is already titled **"T-NEXT-4: Performance Analytics + Attribution +
Portfolio History"**. That is a *different* T-NEXT-4 from this mission's
"Canonical Trading Chain Integration & Execution Integrity". Both exist. This
mission's branch is named `feature/t-next-4-execution-integrity` to keep them
distinguishable; the roadmap should renumber one of them.

## Classification

| Item | Verdict | Reason |
|---|---|---|
| PR #35 T-NEXT-1 canonical paper fund ledger | **KEEP** | Contains `saathi/platform/fund_ledger/` — the canonical ledger this mission depends on. Already contained in trunk-v3. |
| PR #36 T-NEXT-1.1 ledger cutover | **KEEP** | Fill→ledger posting path (`posting.py`). Already in trunk-v3. |
| PR #37 T-NEXT-2 independent risk engine | **KEEP** | `portfolio_risk/`. Already in trunk-v3. |
| PR #41 T-NEXT-3 portfolio construction | **KEEP** | `portfolio_construction/`. Already in trunk-v3. |
| PR #43 T-NEXT-4 performance attribution | **KEEP (rename)** | Valid work; collides by name only. Already in trunk-v3. |
| PR #45 R2 trunk convergence | **KEEP — this is the canonical trunk** | Contains the whole chain. Chosen as the base for this mission. |
| `milestone/m312-m319-connectivity-governance` | **MERGE_LATER** | Holds only the two documentation commits. Merge forward into the trunk; do not build trading work on it. |
| PRs #26–#34 (V-NEXT voice) | **DEFER** | Unrelated plane. |
| PRs #38–#42 (UI-NEXT) | **DEFER** | Unrelated plane, except `ui-next-1` which is the chain root. |
| PR #44 voice convergence | **DEFER** | Unrelated plane. |

## Decision

**Base this mission on `integration/saathios-trunk-v3`** (PR #45, `4756ece`),
in a dedicated worktree at `~/SaathiAI-tnext4`, on branch
`feature/t-next-4-execution-integrity`.

Nothing was merged. No PR was closed, retargeted, or force-pushed. The stacked
chain is left exactly as it was; this mission adds one new branch on top of the
convergence trunk.

## What must converge before this work can land

1. `milestone/m312-m319-connectivity-governance` (2 doc commits) merges forward
   into the trunk — trivial, no conflicts expected in trading paths.
2. The trunk-v3 convergence PR #45 lands, or this branch retargets onto whatever
   supersedes it.
3. The T-NEXT-4 name collision with PR #43 is resolved by renumbering.

None of these blocks the work in this mission, which is additive.
