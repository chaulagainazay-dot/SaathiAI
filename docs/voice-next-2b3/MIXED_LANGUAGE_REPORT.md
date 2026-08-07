# MIXED_LANGUAGE_REPORT

PRIMARY differentiator. Locked mix intent ≥ 0.60, first-span ≥ 0.50, terms ≥ 0.50, CER ≤ 0.50.

| Model | intent | first-span | terms | CER | Gate |
| --- | --- | --- | --- | --- | --- |
| tiny | 0.30434782608695654 | 0.43478260869565216 | 0.1875 | 0.7842109084230743 | FAIL |
| base | 0.43478260869565216 | 0.391304347826087 | 0.34375 | 0.4845732395393982 | FAIL |
| small | 0.5217391304347826 | 0.4782608695652174 | 0.34375 | 0.4183599309133349 | FAIL |

vs 2B.2 NE-only forced-ne mixed intent **0.00** → code-switch small **~0.52**. Progress, still **below 0.60**.

Observed failure modes: Devanagari-phoneticizing English terms; dropping finance tokens; occasional loops (tiny).

