# POST_TRAINING_QUALIFICATION

## Gates (unchanged)

```json
{
  "en_intent_min": 0.7,
  "ne_intent_min": 0.6,
  "mix_intent_min": 0.6,
  "ne_first_span_min": 0.5,
  "ne_cer_max": 0.45,
  "numeric_fidelity_min": 0.7
}
```

## Required eval sets

1. Locked V-NEXT historical corpus (untouched)
2. Owner speech (OWNER_EVAL)
3. New-speaker product-clean test (speaker-disjoint)
4. Noise / short interrupt subsets

## Promotion requires ALL of

```text
ALL LOCKED GATES PASS
+ resource budget pass
+ privacy LOCAL_CONFIRMED
+ license PRODUCT_CLEAN lineage
+ owner real-speech validation
```

Training loss improvement alone is **not** promotion.

## Primary swap rule

Only then:

```text
Local Whisper+adapter = product primary
Browser = fallback
```

