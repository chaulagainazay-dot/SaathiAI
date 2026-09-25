# ECHO_CONTROL

| Measure | Implementation |
| --- | --- |
| getUserMedia AEC/NS/AGC | DEFAULT_MIC_CONSTRAINTS |
| Echo suppression window | ignore barge-in for `echoSuppressionMs` after TTS start |
| Higher barge-in threshold | `bargeInThreshold` vs `speechStartThreshold` |
| Debounce | 120ms between acoustic interrupts |

**Limitation:** loud speakerphone may still false-trigger; headphones safer. Not a perfect AEC.
