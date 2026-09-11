# DATA_QA_SPEC

## Per-clip checks

| Check | Fail action |
| --- | --- |
| sample_rate == 16000 (or resampled) | resample or reject |
| channels == 1 | downmix or reject |
| duration 0.5–40 s | reject |
| clipping (peak ≥ 0.99) | reject |
| leading/trailing silence only | reject |
| transcript empty | reject |
| number mismatch vs prompt | reject |
| wrong bucket / no consent | reject |
| eval corpus ID collision | reject |

## Automation

`tools/voice-stt-train/scripts/qa_manifest.py` validates manifests.

## No LLM auto-fix

Incorrect labels are human-corrected or dropped.

