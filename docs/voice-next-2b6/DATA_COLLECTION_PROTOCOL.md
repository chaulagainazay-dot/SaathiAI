# DATA_COLLECTION_PROTOCOL — V-NEXT-2B.6

## Purpose

Collect a **product-clean**, multi-speaker Nepali–English / code-switch speech corpus sufficient to justify **one** bounded Whisper CS Small LoRA experiment.

This milestone is **data only**. No model training.

## Target composition (approximate)

| Category | Share |
| --- | --- |
| Nepali-only | 20–25% |
| English-only | 15–20% |
| Nepali–English mixed | 35–40% |
| Numeric / financial | 15–20% |
| Short interrupts | 5–10% |

## Pilot thresholds (before training authorization)

| Metric | Minimum | Preferred |
| --- | --- | --- |
| Speakers | 5 | 8–15 |
| Clean MIX clips | 500 | more with diversity |
| Clean numeric clips | 200 | with safety pairs |
| Consent | commercial complete | redistribution optional false default |
| Splits | speaker-disjoint val/test | required |

## Local storage

```text
~/.saathi/stt-product-corpus/
  speakers/spk_NNN/wav/
  consents/spk_NNN.json
  manifests/dataset_manifest.jsonl
```

**Never commit raw audio to Git.**

## Workflow

1. Register speaker consent (`participant_recorder.py register`)
2. Record prompts one at a time (local mic, mono 16 kHz WAV)
3. Human-verify transcripts when wording differs
4. Run `run_pipeline.py` (QA → hash → split → contamination → stats → gate)
5. Freeze only when gate returns `WHISPER_CS_LORA_TRAINING_AUTHORIZED`

## Prompt inventory (repo)

```json
{
  "total_prompts": 739,
  "MIX": 435,
  "EN": 268,
  "NE": 36,
  "numeric": 476,
  "interrupt": 12,
  "financial_flagged": 489
}
```

## Status at certification

Product-clean recorded hours: **0** (tooling + prompts ready; speakers not yet recruited).

Gate: `PRODUCT_CLEAN_DATA_INSUFFICIENT_FOR_TRAINING`

