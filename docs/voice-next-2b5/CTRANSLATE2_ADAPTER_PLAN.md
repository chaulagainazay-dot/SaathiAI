# CTRANSLATE2_ADAPTER_PLAN

## Target path

```text
openai/whisper-small
  + LoRA adapter (PEFT)
        ↓ merge_and_unload()
Whisper Small merged HF
        ↓ ct2-transformers-converter --quantization int8
CTranslate2 model dir
        ↓ faster-whisper WhisperModel(path)
LocalStreamingSttAdapter
```

## Why merge

faster-whisper/CTranslate2 does **not** natively load PEFT adapters. Merge is required for current SaathiOS deployment path.

## Plumbing proof

`tools/voice-stt-train/scripts/prove_ct2_plumbing.py` validates:

1. load base Whisper-small config path
2. create dummy LoRA-compatible state (or skip if offline)
3. document merge + convert commands
4. assert converter CLI present when deps installed

No production training required for plumbing proof.

