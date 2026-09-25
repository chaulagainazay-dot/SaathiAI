# NUMERIC_SPEECH_CURRICULUM

Current champion numeric fidelity ≈ **0.40** (gate ≥ 0.70).

## Forms to cover

| Class | Examples |
| --- | --- |
| Integers | 5, 15, 500, 5000 |
| Decimals | 1.5, 7.25, 0.75 |
| Percent | 5%, five percent, 1.5 percent |
| Currency | NPR 50,000; NPR 5 lakh; fifty thousand |
| Quantities | 500 shares; fifteen shares |
| Negative / direction | reduce by 5%; below 1.5% |
| Dates/times | optional pilot |

## Mixed templates

```text
Position size five percent राख
आजको drawdown seven point five percent छ?
NPR fifty thousand भन्दा माथि नजाऊ
Buy five hundred shares
```

## Sampling

Recommend train mix:

```text
numeric-tagged clips: 15–25% of steps
```

not >40% (avoid collapse of general speech).

## QA

Every numeric clip must have:

```text
canonical_number
surface_form
unit
language_mix
```

Do not LLM-relabel numbers.

