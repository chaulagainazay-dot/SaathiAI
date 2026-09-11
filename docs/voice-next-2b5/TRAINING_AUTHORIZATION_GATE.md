# TRAINING_AUTHORIZATION_GATE

## Minimum data threshold (hard)

| Requirement | Met today? |
| --- | --- |
| product-clean mixed speech exists | **NO** |
| multiple speakers (5+) | **NO** |
| numeric curriculum recorded | **NO** (prompts only) |
| speaker-disjoint val/test | **NO** (no train set yet) |
| consent/provenance complete | **NO** (spec only) |
| no eval contamination | policy ready |

## Result

```text
PRODUCT_CLEAN_DATA_INSUFFICIENT_FOR_TRAINING
```

## Training stop rules (when authorized later)

| Condition | Action |
| --- | --- |
| val loss diverges 3 epochs | stop |
| EN intent drop >0.05 | stop / rollback sampling |
| numeric fidelity falls on val | increase numeric weight carefully |
| NaN / Inf | abort |
| wall-clock / cost budget exceeded | stop |

## Explicit non-authorization

This milestone does **not** authorize paid GPU jobs or production weight training.

