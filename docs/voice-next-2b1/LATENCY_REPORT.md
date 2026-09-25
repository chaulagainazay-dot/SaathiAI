# LATENCY_REPORT

## Decode latency (utterance file → final text)

Measured on offline file decode (not live streaming partials). Sample n=31 per model.

| Model | p50 | p95 | worst | note |
| --- | --- | --- | --- | --- |
| tiny | 0.17 s | 0.89 s | 5.56 s | cold outliers on first/long |
| base | 0.33 s | 1.56 s | 6.36 s | acceptable for turn finalization |
| small | 1.13 s | 2.10 s | 18.5 s | too heavy for interactive turns on 8 GB |

## Streaming partials

faster-whisper is **pseudo-streaming** (chunk/VAD segment). True first-partial latency for live mic was **not** fabricated from offline file stats.

For live path (when qualified):

| Metric | Status |
| --- | --- |
| speech start → first partial | UNMEASURED live (owner tool) |
| speech start → first useful partial | UNMEASURED live |
| speech end → final transcript | approximate = decode_s above |
| speech end → TurnCoordinator finalization | + endpointGrace (~200 ms) after STT final |

## TurnCoordinator synthetic

Unit tests: silence false-interrupt timeout 20–900 ms configurable; STT final path immediate.

## Do not claim

- No p50/p95 from <3 live mic samples claimed as production SLOs

