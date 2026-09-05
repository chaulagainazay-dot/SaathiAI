# TURN_COORDINATOR

Signals: VAD start/end, STT partial/final, silence endpoint, punctuation/heuristic completeness, backchannel regex.

Outputs turn with `isExecutable` / `isBackchannel`. Never executes tools.
