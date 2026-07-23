# M49.4 Milestone Chain Reconstruction

## Purpose

Prove the M48 → M49.1 → M49.2 → M49.3 → M49.4 ancestry with Git evidence, not PR UI alone.

## Chain tips (verified 2026-07-23)

| Milestone | Branch | Final / tip commit | PR | Base | Head |
|---|---|---|---|---|---|
| M48 / M48.5 | `milestone/m48-agent-runtime-baseline` | `27b3bcf3ac58f92558c3b2c466a33c09dc823d14` | #3 | `master` | same |
| M49.1 | `milestone/m49-tool-execution-framework` | `f41e756c169b3899cb96a6b922d990472df13433` | #4 | m48 baseline | same |
| M49.2 | `milestone/m49-2-tool-convergence` | `d8492a8993de6ea4e83c59d9aea37440e1676ee3` | #5 | m49.1 | same |
| M49.3 | `milestone/m49-3-gateway-completion` | `0eb1592caa207ca61b250ec50a8fc9c6a3d1ba3c` | #6 | m49.2 | same |
| M49.4 start | `milestone/m49-4-runtime-closure` | starts at M49.3 tip | draft | m49.3 | this branch |

`master` tip at reconstruction: `67efcb3cd5ca52c2fb96052168253fdf286ff60a` (ancestor of M48).

## Ancestry proofs

```text
git merge-base --is-ancestor 27b3bcf f41e756  → YES (M48 ⊂ M49.1)
git merge-base --is-ancestor f41e756 d8492a8  → YES (M49.1 ⊂ M49.2)
git merge-base --is-ancestor d8492a8 0eb1592  → YES (M49.2 ⊂ M49.3)
git merge-base --is-ancestor 27b3bcf 0eb1592  → YES (M48 ⊂ M49.3)
git merge-base --is-ancestor master milestone/m48-agent-runtime-baseline → YES
commits on master not in M49.3: 0
commits M48..M49.3: 16
commits master..M49.3: 23
```

## Dependency order

```text
master
  └─ PR#3 M48 agent runtime baseline
       └─ PR#4 M49.1 canonical tool framework
            └─ PR#5 M49.2 migration + durable idempotency
                 └─ PR#6 M49.3 gateway completion
                      └─ PR#? M49.4 runtime closure (this branch)
```

## CI evidence (latest successful PR runs)

| PR | critical-regressions | full-suite | run |
|---|---|---|---|
| #3 | pass | pass | 29992750196 |
| #4 | pass | pass | 29993948781 |
| #5 | pass | pass | 29997761579 |
| #6 | pass | pass | 30002010832 |

Earlier failed/cancelled runs on the same branches are superseded by the successful runs above.

## Drift detection

| Check | Result |
|---|---|
| Parallel branch drift vs master | None — master has 0 unique commits ahead of M49.3 |
| Duplicate commits | Not observed; linear stacked history |
| Missing commits | None in chain |
| Unexpected cherry-picks | None detected |
| Base mismatch vs PR JSON | None — PR bases match branch stack |
| Documentation-only tip differences | M49 tips include docs commits as final SHAs (expected) |

## Integration implication

The integrated M48–M49.3 product is exactly the tip of `milestone/m49-3-gateway-completion`.
M49.4 adds only closure audits, residual tightenings, and certification docs on that tip.
