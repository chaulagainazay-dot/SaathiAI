# SEMANTIC_TURN_OPTIONS

## Reference pattern (LiveKit-style)

```text
VAD + transcription + turn detector + endpointing + adaptive interruption
```

## Options

| Option | Class | Notes |
| --- | --- | --- |
| Fixed silence + STT final + VAD (current) | **KEEP / implement now** | Production path |
| Expanded backchannel + completeness heuristics | **implement now** | Done in 2B.1 |
| Local lightweight turn-end classifier | **adapt later** | Only if false finals high after owner live |
| LiveKit Agents cloud turn detector | **reject** (without explicit auth) | Cloud dependency |
| Pipecat interruption scheduler | **defer** | Revisit in 2C decision |
| LLM-based turn classifier | **defer** | Too heavy for 8 GB default |

## Decision

No cloud-only turn detector. No new framework this mission.

