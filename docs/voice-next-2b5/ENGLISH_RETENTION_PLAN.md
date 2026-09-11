# ENGLISH_RETENTION_PLAN

Champion English intent ≈ **0.80** (must stay ≥ 0.70).

## Measures

1. **EN replay** in every epoch (Common Voice EN CC0 / clean EN prompts).
2. **Early-stop metric:** EN intent on holdout; stop if drops >0.05 absolute.
3. **Mix-first loss balance** — do not train only on NE.
4. Optional: freeze encoder for 1 epoch, then unfreeze LoRA on full stack (experimental).

## Monitoring

| Checkpoint | Action if EN intent < 0.70 |
| --- | --- |
| mid-train | reduce NE sampling; increase EN |
| final | **reject** promotion; do not deploy |

