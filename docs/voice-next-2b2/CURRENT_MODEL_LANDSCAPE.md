# CURRENT_MODEL_LANDSCAPE — V-NEXT-2B.2

Fresh research (2026-08-07) for Nepali-specialized local ASR.

## Priority candidates (Whisper Small family)

| Model | Params | Training | Self-reported | Format |
| --- | --- | --- | --- | --- |
| **Dragneel/whisper-small-nepali** | 244M | OpenSLR 54 ~154h | WER 26.69% on OpenSLR test (**self-reported**) | HF Transformers → CT2 |
| **sparshrestha/finetuned-whisper-small-nepali** | 244M | Common Voice 26 + FLEURS ne | WER ~63% eval (**self-reported**) | HF → CT2 (tokenizer fix) |
| **devrahulbanjara/whisper-small-nepali** | 244M | amitpant7 corpus | limited card | HF → CT2 (runtime unstable) |
| Dragneel/whisper-medium-nepali-openslr-ct2 | ~769M | OpenSLR 54 | prebuilt CT2 | Medium — heavy for 8 GB |
| kiranpantha/whisper-large-v3-turbo-nepali | large | various | CT2 available | **REJECT primary** (size) |
| Dragneel/whisper-large-v3-nepali-openslr | large-v3 | OpenSLR | — | **REJECT primary** |
| sidskarki/Qwen3-ASR-Nepali | ~1.7B | OpenSLR 54 | avg WER 41.4% cross-set (**self-reported**) | CUDA-oriented; **RESEARCH_COMPARATOR** |
| wav2vec2/XLS-R Nepali variants | 300M-class | various | mixed | Different runtime; DEFER |
| sherpa-onnx Nepali | — | no first-class NE streaming found | — | DEFER |

## V-NEXT-2B.1 baseline (preserved — not re-run as primary)

Generic faster-whisper tiny/base/small failed locked NE gate. Not re-tested for a different answer.

