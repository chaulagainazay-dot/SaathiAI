# voice-stt-data — Product-clean multi-speaker speech collection

V-NEXT-2B.6 tooling for SaathiOS Nepali–English / code-switch speech.

## Principles

- Raw audio lives **only** under `~/.saathi/stt-product-corpus/`
- Git holds prompts, schemas, templates, derived stats, and docs — **never** WAVs
- Commercial product training requires `commercial_model_training_allowed=true`
- Default `redistribution_allowed=false`
- No auto-upload, no cloud STT, no LoRA launch from this package

## Layout

```text
tools/voice-stt-data/
  prompts/          # SaathiOS-owned prompt manifests
  schemas/          # consent + clip JSON schemas
  templates/        # human-readable consent statement
  scripts/          # recorder + QA + splits + gate
  tests/
```

## Participant flow

```bash
# 1. Register consent (commercial required for PRODUCT_CLEAN)
python3 tools/voice-stt-data/scripts/participant_recorder.py register \
  --speaker-id spk_001 --commercial --research --evaluation

# 2. Record one prompt at a time (local mic via ffmpeg)
python3 tools/voice-stt-data/scripts/participant_recorder.py record \
  --speaker-id spk_001 --seconds 5 --device mac_builtin --noise quiet

# 3. Human-verify transcript if wording differed
python3 tools/voice-stt-data/scripts/verify_transcript.py \
  --clip-id spk_001_mix_001_t01 --transcript "आजको portfolio risk explain गर"

# 4. Pipeline
python3 tools/voice-stt-data/scripts/run_pipeline.py
```

## Authorization gate

```bash
python3 tools/voice-stt-data/scripts/training_authorization_gate.py --update-train-manifest
```

Hard thresholds:

| Requirement | Value |
| --- | --- |
| Speakers (commercial) | ≥ 5 (prefer 8–15) |
| Clean MIX clips | ≥ 500 |
| Clean numeric clips | ≥ 200 |
| Speaker-disjoint holdout | required |
| RESEARCH_ONLY in TRAIN | 0 |
| Contamination | CLEAN |

Success verdict:

```text
WHISPER_CS_LORA_TRAINING_AUTHORIZED
```

Until then, training remains blocked:

```text
PRODUCT_CLEAN_DATA_INSUFFICIENT_FOR_TRAINING
```

## Explicit non-actions

- No Hugging Face Jobs
- No local LoRA / fine-tuning
- No streaming TTS / wake word / language router
- No ExecutionGateway or Trading Guardian changes
- No raw audio commits
