# BENCHMARK_CONTAMINATION_POLICY

## Never train on

| Corpus | Reason |
| --- | --- |
| V-NEXT-2B.1 locked TTS eval | historical holdout |
| V-NEXT-2B.3 codeswitch eval set | historical holdout |
| Numeric eval IDs used for gates | holdout |
| Owner eval subset tagged OWNER_EVAL | personal holdout |

## Manifest hashes

`TRAINING_MANIFEST.json` records:

```text
dataset_revision
content_hash
excluded_eval_hashes
```

## CI

`tools/voice-stt-train/tests/test_no_contamination.py` checks exclusion lists.

