# Performance Baseline (M13.5)

Real single-sample measurements (local, macOS, current db sizes). Where only one
sample exists, p95 is NOT reported (per honesty requirement). Prior-milestone
numbers are cited from their own reports.

## Ops (M13.5, measured this milestone)
| Operation | Median (1 sample) |
|---|---|
| Backup (5 app dbs, ~1.2MB total) | 32 ms |
| Restore + full verify (checksums + integrity) | 4 ms |
| Storage scan + threshold report | 2.1 ms |
| DB integrity_check (all 5 dbs) | 1.3 ms |
| Config check (secret-redacted) | 9.8 ms |
| FFmpeg slate render (320x240, 1s) | 178 ms (M13) |

## Prior milestones (from their reports)
- Full test suite: ~6m30s (1122 tests, M13).
- Memory hybrid retrieve top-10 / 10k: 177 ms (M9).
- Agent run creation: 11 ms; 1000-event load: 2.7 ms (M10).
- Chat send pipeline overhead (excl model): 53 ms (M8).
- Voice: VAD 0.75ms/1s; faster_whisper warm 202ms/2s; say TTS ~3.4s fixed (M12).
- Studio full 11-artifact short-video workflow: seconds (M13).

## Notes
- p95/load numbers require a soak run with many samples; a bounded soak was NOT
  run this milestone (would risk local machine stability without a configured
  ceiling). Recommended as a CI/staging job.
- `say` TTS ~3.4s fixed overhead exceeds the 2s first-audio target and is
  macOS-only — documented in STAGING_DEPLOYMENT_ARCHITECTURE.md.
