# VOICE_NAVIGATION

## VoiceSession states (do not invent)

`IDLE | READY | LISTENING | TRANSCRIBING | THINKING | SPEAKING | INTERRUPTING | DEGRADED | ERROR`

## Example command flows

| Utterance | Focus | Response |
| --- | --- | --- |
| show portfolio risk | INVESTMENTS + risk panel | risk_status + budgets |
| why is risk elevated | risk + reason_codes | explain codes |
| show active missions | AGENTS | topology ACTIVE |
| what needs approval | ATTENTION | queue |
| ten percent stress | risk stress DEMO/real | stress_loss |
| show evidence | EVIDENCE | timeline |
| go back to command | COMMAND | mode switch |
| stop | barge-in | INTERRUPTING |

Pipeline:

```text
speech → transcript → intent/context → visual focus → answer
```

