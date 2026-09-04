# VOICE_SESSION_CONTRACT

States implemented truthfully:

`IDLE | READY | LISTENING | TRANSCRIBING | THINKING | SPEAKING | INTERRUPTING | DEGRADED | ERROR | CLOSED`

Reserved (not faked): `SPEECH_DETECTED` until VAD.

Snapshot fields: sessionId, state, inputState, outputState, transcriptPartial/Final, assistantText, timestamps, interruptible, providers, error, capabilities, claim ids.

Capabilities default: manualInterrupt=true; vad/wake/fullDuplex/streaming=false.
