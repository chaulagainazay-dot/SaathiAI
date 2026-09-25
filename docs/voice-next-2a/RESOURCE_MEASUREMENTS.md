# RESOURCE_MEASUREMENTS

Synthetic probe (5000 frames × 512 samples, energy VAD only):

```json
{
  "frames": 5000,
  "totalMs": 8.102,
  "perFrameMs": 0.0016,
  "rss": 53395456,
  "heapUsed": 4934408
}
```

| Scenario | Expectation |
| --- | --- |
| Idle without VAD | baseline |
| Active energy VAD | sub-ms per frame typical on Apple Silicon |
| Silero ONNX | not loaded this milestone |

No GPU dependency. No competition with local LLM weights this mission.
