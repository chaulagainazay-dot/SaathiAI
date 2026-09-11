# CANDIDATE_SELECTION

## Selected for local benchmark

1. **Dragneel/whisper-small-nepali** → CT2 int8 (primary specialized)
2. **sparshrestha/finetuned-whisper-small-nepali** → CT2 int8 (independent control)
3. **devrahulbanjara/whisper-small-nepali** → CT2 attempted (runtime failed)

## Not loaded

| Candidate | Reason |
| --- | --- |
| Qwen3-ASR-Nepali 1.7B | RESEARCH_COMPARATOR; memory + community-use license |
| Whisper Large V3 Nepali | exceeds 8 GB multi-stack budget |
| Moonshine | no Nepali |
| Generic tiny/base/small re-run | forbidden by mission (already failed) |

## Resource estimates (pre-download)

| Model | Disk CT2 | Expected RSS |
| --- | --- | --- |
| Whisper Small CT2 int8 | ~250 MB | ~0.9–1.1 GB peak |
| Medium CT2 | larger | ~1.5–2 GB — conditional only |

