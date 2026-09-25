# voice-stt-train — Whisper CS Small LoRA readiness

**Status:** readiness package only. Training is **blocked** until product-clean multi-speaker code-switch data exists and authorization flags flip.

## Layout

```text
configs/lora_whisper_small.yaml
TRAINING_MANIFEST.json
prompts/product_clean_prompts.jsonl
scripts/
  validate_authorization.py
  train_lora_whisper.py
  qa_manifest.py
  check_contamination.py
  prove_ct2_plumbing.py
tests/test_training_readiness.py
```

## Hard rules

1. Do not train on the 8 GB Mac.
2. Do not train on locked V-NEXT evaluation corpora.
3. Do not use CC BY-NC code-switch public data for product weights.
4. Do not launch paid HF Jobs without owner authorization.

## Check readiness

```bash
python scripts/validate_authorization.py   # expect exit 2 today
python -m unittest tests/test_training_readiness.py
python scripts/prove_ct2_plumbing.py
```
