# FINAL_CERTIFICATION — V-NEXT-2B.5

## Terminal verdict

```text
PRODUCT_CLEAN_DATA_INSUFFICIENT_FOR_TRAINING
```

## What is ready

- LoRA selected over full FT
- Data buckets + consent/provenance specs
- Common Voice NE classified PRODUCT_CLEAN (CC0)
- NC code-switch corpus excluded from product train
- Numeric curriculum designed
- Split + contamination policies
- Reproducible training package under `tools/voice-stt-train/`
- CT2 merge deployment plan
- HF Jobs plan (no launch)
- Post-training gates unchanged

## What is missing

```text
product-clean multi-speaker Nepali–English mixed recordings
```

Without that, LoRA cannot be expected to clear MIX/NE gates legally and safely.

## Champion preserved

```json
{
  "name": "Bijay13 Whisper Small NE\u2013EN v3.1",
  "en_intent": 0.8,
  "ne_intent": 0.57,
  "mix_intent": 0.52,
  "numeric": 0.4,
  "peak_rss_mib": 1400
}
```

## Non-actions

actual model training = false · streaming TTS = false · language router = false · wake word = false · cloud STT = false · master merge = false

