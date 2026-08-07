# Strategy qualification methodology (M190)

## Allowed verdicts

`INSUFFICIENT_EVIDENCE` | `RESEARCH_ONLY` | `PAPER_ELIGIBLE` | `PAPER_APPROVAL_REQUIRED` | `PAPER_SUSPENDED` | `REJECTED`

**No live-trading verdict exists.**

## Scorecard dimensions (visible)

evidence quality · robustness · drawdown control · cost resilience · regime stability · parameter stability · operational integrity · risk containment

Weighted score is optional transparency only — never sole gate.

## PAPER_ELIGIBLE

Requires all `QualificationGates` mandatory conditions (26 operational checks + owner approval still required).

Restrictions (regimes/markets) may be attached as metadata without inventing new live verdicts.

## Kotegawa-inspired strategy

Public-principles interpretation only — not an exact copy of Takashi Kotegawa’s method.
Evaluated across regime segments (bear, event risk, high vol, etc.).
Unfavorable results are reported honestly; strategy is not protected from failure.
