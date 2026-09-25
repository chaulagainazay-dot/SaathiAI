# NEXT_VOICE_ARCHITECTURE_DECISION

## After STT qualification

Recommended **single** next mission:

```text
V-NEXT-2B.2 — MULTILINGUAL LOCAL STT HARDENING
```

Rationale: TTS + English are not the blocker; **Nepali accuracy** is. Streaming TTS (2C) would amplify wrong transcripts. Semantic turn detector alone does not fix language accuracy.

## Alternatives considered

| Mission | Why not now |
| --- | --- |
| V-NEXT-2C streaming TTS | Premature while STT NE fails |
| V-NEXT-2B.2 semantic turn detector only | Secondary to NE STT quality |
| Pipecat integrate | Not justified (see below) |

## Pipecat / LiveKit re-eval

| Framework | Verdict |
| --- | --- |
| Pipecat | **DEFER** — useful patterns (frame pipeline, pre-roll, metrics) already mirrored in SaathiOS coordinator; dependency cost not justified for a small scheduler |
| LiveKit Agents | **ADAPT** concepts only; reject cloud turn detector without auth |

## Technology classes (post-measure)

| Tech | Class |
| --- | --- |
| whisper.cpp | ADAPT (Metal path later) / COMBINE |
| faster-whisper | ADAPT (EN-optimized experimental) |
| WhisperKit | DEFER |
| Moonshine | REJECT primary |
| sherpa-onnx | DEFER |
| browser STT | KEEP fallback / product primary until local qualifies |
| Pipecat | DEFER |
| LiveKit | ADAPT concepts |

