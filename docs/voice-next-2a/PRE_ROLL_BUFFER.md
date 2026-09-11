# PRE_ROLL_BUFFER

- Default ~280ms at 16 kHz conceptual rate
- In-memory Float32 chunks only
- Cleared on session close / disarm
- Never written to disk
- Snapshot available via `getPreRollSamples()` for future STT (V-NEXT-2B)
