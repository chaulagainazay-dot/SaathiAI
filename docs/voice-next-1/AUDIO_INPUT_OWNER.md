# AUDIO_INPUT_OWNER

Module: `saathi-os/lib/voice-session/input-owner.js`

- `acquireInputClaim({ label })` — exclusive; preempts prior
- `openMicrophoneForClaim(claim)` — getUserMedia bound to claim
- `forceReleaseInput(reason)` — route/logout
- Tracks MediaStream tracks + SpeechRecognition handle
- Telemetry: input_acquired / started / released / preempt
