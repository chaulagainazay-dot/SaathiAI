# OWNER_CORPUS_COMPLETION

## Storage

`~/.saathi/stt-owner-corpus/` (raw audio **not** committed)

## Tooling

- `complete_owner_corpus.py` — batch record + RMS speech detection
- Subjective ratings **not** auto-filled

## Results

```json
{
  "total": 17,
  "speech_detected": 15,
  "ambient_or_silent": 2,
  "failed": 0,
  "complete_for_tooling": true,
  "complete_for_intentional_owner_accent": false,
  "rms_threshold": 0.01
}
```

| Metric | Value |
| --- | --- |
| Total prompts | 17 |
| Speech detected (RMS≥0.01) | 15 |
| Ambient/silent | 2 |
| Failed records | 0 |
| Tooling complete | True |
| Intentional accent complete | False |

**Note:** RMS detection is a proxy; human review of content is still required for true owner-accent certification. Ambient items excluded from owner accent scoring.

