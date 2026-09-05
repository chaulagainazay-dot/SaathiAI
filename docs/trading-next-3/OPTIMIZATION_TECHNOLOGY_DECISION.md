# OPTIMIZATION_TECHNOLOGY_DECISION

| Library | Verdict | Rationale |
| --- | --- | --- |
| PyPortfolioOpt | DEFER | Heavy; non-deterministic solvers; overkill |
| Riskfolio-Lib | DEFER | Same |
| cvxpy | DEFER | Solver stack / memory on 8 GB host |
| LEAN patterns | ADAPT (ideas only) | Patterns for equal/fixed; not integrated |
| Qlib strategies | DEFER | Research stack |
| **In-repo constructors** | **KEEP** | Deterministic, low memory, auditable |

No advanced optimization dependency added in T-NEXT-3.

