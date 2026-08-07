# OWNER_STT_QUALIFICATION

## Purpose

Owner-run live mic qualification. **Do not auto-fill owner judgments.**

## Tool

```bash
cd tools/voice-stt-bench
source .venv/bin/activate
# optional future: python owner_qualify.py
```

Until interactive helper is expanded, use:

1. Record each utterance from MULTILINGUAL_EVALUATION_CORPUS.md on the laptop mic (quiet room).
2. Save WAV 16 kHz mono under `corpus/owner_wav/`.
3. Run `STT_MODELS=base python benchmark_stt.py` against owner files (manifest extension).
4. Mark each item:

| Field | Owner fills |
| --- | --- |
| intent_ok | Y/N |
| proper_nouns_ok | Y/N |
| accent_notes | free text |
| usable_as_primary | Y/N |

## Timing

Script measures decode timing automatically; owner only scores subjective accuracy.

## Pass criterion

Same locked Nepali gate as automated bench + owner `usable_as_primary` majority on NE_CMD + MIX.

## Status

Owner live run: **PENDING** (not auto-filled).

