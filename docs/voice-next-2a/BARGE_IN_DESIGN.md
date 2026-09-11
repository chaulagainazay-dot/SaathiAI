# BARGE_IN_DESIGN

While `SPEAKING`:

1. Single mic claim retained or opened for monitor
2. VAD in barge-in mode (higher threshold)
3. Echo suppression window after TTS start (~220ms default)
4. On confirmed speech → `interrupt("ACOUSTIC_SPEECH")`
5. Output released; input preserved; pre-roll retained in memory
6. Latency recorded (p50/p95 in barge-in health)

Manual interrupt remains always available.
