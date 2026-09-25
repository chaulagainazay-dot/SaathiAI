# HUGGINGFACE_JOBS_PLAN

## Role

Optional remote backend for LoRA training **after** data threshold + owner authorization.

## Pros

- reproducible UV/pip env
- artifact registry
- no local GPU

## Cons

- paid GPU minutes
- secrets for HF token
- data upload privacy

## Prepared assets

```text
tools/voice-stt-train/scripts/train_lora_whisper.py
tools/voice-stt-train/configs/lora_whisper_small.yaml
tools/voice-stt-train/TRAINING_MANIFEST.json
```

## Explicit rule

```text
DO NOT LAUNCH PAID JOB without separate owner authorization
```

## Alternatives

| Backend | Use |
| --- | --- |
| Colab (free/pro) | smoke / small runs |
| Kaggle | limited hours |
| HF Jobs | preferred paid path when authorized |

