# STREAMING_COMPATIBILITY

| Capability | Omni CTC 300M |
| --- | --- |
| True streaming partials | **No** (batch offline) |
| Max audio | **40 s** hard limit (official) |
| Pre-roll PCM ingest | Possible only via offline file/chunk pipeline |
| Cancellation | Process-level only |
| Fit to StreamingTranscriptionAdapter | **Poor** without chunked pseudo-stream redesign |

Do **not** force into production StreamingTranscriptionAdapter without redesign.

