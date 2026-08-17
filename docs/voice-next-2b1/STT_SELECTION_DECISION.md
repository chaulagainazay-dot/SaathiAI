# STT_SELECTION_DECISION

## Decision

```text
MULTILINGUAL_LOCAL_STT_NOT_YET_QUALIFIED
```

No local engine met the **pre-locked** Nepali acceptance gate on this host with measured models.

## Hierarchy (product)

| Role | Engine | Notes |
| --- | --- | --- |
| PRIMARY (product) | Browser SpeechRecognition | Compatibility; privacy PLATFORM_MANAGED_UNKNOWN |
| EXPERIMENTAL_LOCAL | faster-whisper base | ENGLISH_OPTIMIZED_OPTION only; explicit request + admission |
| FALLBACK | Manual text / push-to-talk | Always |
| CLOUD | **none** | Never |

## When NE gate later passes

Intended primary: local Whisper family (faster-whisper or whisper.cpp Metal) **base** or better NE-specialized model, with browser fallback.

## Why not primary local now

| Model | NE intent | Gate |
| --- | --- | --- |
| tiny | 0.14 | FAIL |
| base | 0.00 | FAIL |
| small | 0.00 | FAIL |

## Best English local (non-primary)

**faster-whisper base** — intent 0.94 EN, ~830 MiB peak, p50 decode ~0.33 s.

