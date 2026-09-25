# TURN_QUALITY_REPORT

## Hardening (V-NEXT-2B.1)

| Area | Change |
| --- | --- |
| Partial/final ordering | Regressive partial ignore after final |
| Silence endpoint | Unchanged multi-signal (VAD + STT + silence) |
| Transcript finality | preferSttFinal; normalizeTurnText |
| Punctuation | looksSyntacticallyComplete includes Devanagari danda |
| Backchannels | Expanded EN + NE particles; non-executable |
| False interrupt | STT evidence window retained |
| Engine neutrality | `normalizeTranscriptEvent` strips provider quirks |

## Tests

- Partial never executable
- Backchannel `ठीक छ` / `हजुर` non-executable
- Real vs false interruption classification
- Nepali/mixed meaningfulness

## Not claimed

Adaptive conversational interruption (LiveKit-style turn detector model) — deferred (see SEMANTIC_TURN_OPTIONS.md).

