# STT_SELECTION_DECISION

## Verdict input

No Nepali-specialized local model passed locked gate.

## Product hierarchy (unchanged product primary)

| Role | Engine |
| --- | --- |
| PRIMARY | Browser SpeechRecognition (PLATFORM_MANAGED_UNKNOWN) |
| EXPERIMENTAL | faster-whisper generic base (EN) or specialized small (research only) |
| FALLBACK | Manual text |
| CLOUD | none |

## Partial status labels

```text
NO_LOCAL_STT_QUALIFIED
```

Not:

- LOCAL_MULTILINGUAL_STT_QUALIFIED
- NEPALI_LOCAL_STT_QUALIFIED (intent 0.15 << 0.60)

## Language routing

**Not implemented.** Mixed failure under NE-forced decode suggests routing may be needed later — only after a pure-NE model clears gate and EN path remains strong.

