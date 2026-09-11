# V-NEXT-2B.6A — SaathiOS Speech Data Collection Campaign

## Status

```text
PRODUCT_SPEECH_COLLECTION_BLOCKED
```

Engineering (V-NEXT-2B.6) is complete. This campaign exists only to collect **real** multi-speaker speech.

## Why blocked

Autonomous collection cannot satisfy the authorization gate without **live human speakers**:

| Need | Autonomous agent |
| --- | --- |
| ≥5 commercially consented distinct speakers | Requires real people |
| Natural Nepali–English code-switch speech | Requires live speech |
| `human_verified=true` transcripts | Requires human review |
| No fabrication | TTS / synthetic multi-speaker **not** accepted as PRODUCT_CLEAN multi-speaker natural speech |

Owner private corpus (`~/.saathi/stt-owner-corpus/`, ~17 clips) remains **OWNER_PRIVATE** single-speaker and must **not** be silently re-bucketed as multi-speaker PRODUCT_CLEAN.

## Split plan (decided before recording)

| Speaker | Planned split |
| --- | --- |
| spk_001 | TRAIN |
| spk_002 | TRAIN |
| spk_003 | TRAIN |
| spk_004 | VALIDATION |
| spk_005 | TEST |

Principle: **test speaker never appears in train**.

`build_splits.py` with speakers `spk_001`…`spk_005` naturally yields the same mapping (last → TEST, second-last → VAL).

## Per-speaker targets (accepted)

| Bucket | Clips |
| --- | --- |
| MIX | 100–110 |
| numeric/financial | 40–45 |
| NE | 15–20 |
| EN | 15–20 |
| interrupt | 5–10 |

Priority: MIX+numeric → MIX → financial terms → NE → EN → interrupts.

## Operator runbook (when humans are available)

```bash
# 0. Generate assignments (once)
python3 tools/voice-stt-data/scripts/assign_prompts.py

# 1. Register each speaker (commercial REQUIRED)
python3 tools/voice-stt-data/scripts/participant_recorder.py register \
  --speaker-id spk_001 --commercial --research --evaluation

# 2. Record next assigned prompt (human speaks into mic)
python3 tools/voice-stt-data/scripts/campaign_session.py record-next \
  --speaker-id spk_001 --seconds 5 --device mac_builtin --noise quiet

# 3. Human-verify transcript (actual speech)
python3 tools/voice-stt-data/scripts/verify_transcript.py \
  --clip-id <clip_id> --transcript "<what was actually said>"

# 4. After each speaker/batch
python3 tools/voice-stt-data/scripts/run_pipeline.py
python3 tools/voice-stt-data/scripts/campaign_progress.py
python3 tools/voice-stt-train/scripts/validate_authorization.py
```

Stop only when:

```text
WHISPER_CS_LORA_TRAINING_AUTHORIZED
```

## Explicit non-actions (this campaign)

```text
LoRA training = false
full fine-tuning = false
HF Job launch = false
language router = false
streaming TTS = false
wake word = false
cloud STT = false
fabricated multi-speaker audio = false
```

## Next

1. Recruit 5 speakers with commercial consent.
2. Execute assignment lists (~191 prompts/speaker target).
3. Human-verify every accepted clip.
4. Re-run gate → freeze `SAATHI_STT_PRODUCT_CORPUS_V1` only if authorized.
5. Only then: **V-NEXT-2B.7** (do not start training from this campaign).
