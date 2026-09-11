# SPLIT_REPORT

## Policy

- TRAIN / VALIDATION / TEST
- Prefer **speaker-disjoint** validation and test
- At minimum: no TEST speaker appears in TRAIN
- Exact audio SHA duplicates cannot cross splits

## Tool

`tools/voice-stt-data/scripts/build_splits.py`

## Current status

```text
eligible_speakers = 0
speaker_disjoint = false
training_split_ready = false
```

With fewer than 5 PRODUCT_CLEAN speakers, splits remain **UNASSIGNED** and training stays blocked.

