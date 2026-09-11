# MIXED_LANGUAGE_REPORT

## Test phrases (corpus MIX + related)

Examples: portfolio/risk/NAV/Trading Guardian/approvals mixed with Nepali.

## Dragneel (lang=ne policy)

| Metric | mixed |
| --- | --- |
| intent | **0.00** |
| CER | 0.98 |
| term preservation | 0.00 |

Hypotheses often fully Devanagari-phoneticize English terms (e.g. ExecutionGateway → Devanagari approximation).

## Implication

Even if pure NE improved, **mixed is unusable** as universal primary under NE-forced decoding.

Possible future classes (not implemented):

```text
NEPALI_PRIMARY
ENGLISH_PRIMARY
LANGUAGE_ROUTED
```

Preferred: single model that handles mixed — **not achieved**.

