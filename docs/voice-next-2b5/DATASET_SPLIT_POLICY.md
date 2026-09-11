# DATASET_SPLIT_POLICY

## Splits

| Split | Purpose |
| --- | --- |
| TRAIN | LoRA updates |
| VALIDATION | early stop / hyperparams |
| TEST | product-clean holdout |
| OWNER_PERSONAL_TEST | owner accent only |

## Rules

1. **Speaker-disjoint** train vs val/test where feasible.
2. No speaker >40% of TRAIN hours.
3. Locked V-NEXT historical corpora **never** in TRAIN/VAL.
4. Numeric clips stratified across splits.
5. Code-switch density roughly balanced in val/test.

## Leakage tests

Scripts must fail CI if any `utt_id` or audio hash appears in both train and locked eval.

