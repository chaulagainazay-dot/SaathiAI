# NEPALI_REPORT

Locked: intent≥0.60, first-span≥0.50, CER≤0.45

| Model | intent | first-span | CER | Gate |
| --- | --- | --- | --- | --- |
| tiny | 0.42857142857142855 | 0.7142857142857143 | 0.5176065601065601 | FAIL |
| base | 0.5714285714285714 | 0.7142857142857143 | 0.43852314352314353 | FAIL |
| small | 0.5714285714285714 | 0.7142857142857143 | 0.44469289969289966 | FAIL |

Best NE intent ≈ **0.57** (near gate, **not** lowered to pass). Improvement vs 2B.2 specialized NE-only (~0.15–0.29).

