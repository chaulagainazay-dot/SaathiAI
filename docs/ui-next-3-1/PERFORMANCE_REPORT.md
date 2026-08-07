# PERFORMANCE_REPORT — UI-NEXT-3.1

Target: 8 GB Apple Silicon · `/command` must not be continuously expensive while idle.

## Bundle

| Artifact | Size (approx) |
| --- | --- |
| `app/command/page-*.js` | ~70 KB |
| command CSS chunk | ~21 KB |
| GSAP | **not shipped** |
| Lottie | **not shipped** |
| Three.js | **not shipped** |

Delta vs UI-NEXT-3: CSS tokens + presentation helpers only (no animation runtime).

## Runtime

| Metric | Result |
| --- | --- |
| Idle continuous animation | None (unless voice actively LISTENING/SPEAKING/THINKING/TRANSCRIBING) |
| Risk permanent pulse | Rejected — one-shot flash on transition only |
| Chart | Tabular metrics; no WebGL / 3D |
| Interaction latency | CSS transitions ≤250ms; mode enter ≤200ms |

## Decision

```text
PRODUCTION_MOTION_PERFORMANCE acceptable for 8 GB host
```
