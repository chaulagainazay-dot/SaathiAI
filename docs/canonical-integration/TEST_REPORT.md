# TEST_REPORT — Canonical Baseline Integration

**Date:** 2026-08-07  
**Branch:** `integration/saathios-canonical-baseline`  
**Code tip (M17 integrated):** `272dbd5d0b9495d9682955074a76b4931e440daf`

## Level A — Static

| Check | Result |
| --- | --- |
| `git diff --check` (e1738d7..HEAD) | PASS |
| `python -m compileall saathi tests` | PASS |

## Level B — M17 mandatory

### `tests/test_m17_17_scheduled_graph_recovery.py`

| Iteration | Collected | Passed | Failed | Skipped | Duration |
| --- | --- | --- | --- | --- | --- |
| 1 | 36 | 36 | 0 | 0 | ~1.74s |
| 2 | 36 | 36 | 0 | 0 | ~1.58s |
| 3 | 36 | 36 | 0 | 0 | ~1.59s |

Includes: concurrent dispatch, concurrent recover (2 and 10 callers), idempotency, cancellation/approval fail-closed, no trading surface, scheduler isolation from direct graph executor.

### Stress harness `scripts/m17_scheduled_graph_concurrency_stress.py`

| Workers | Iterations | Successes | Failures | Duplicate graphs | Orphans | Duration |
| --- | --- | --- | --- | --- | --- | --- |
| 2 | 100 | 100 | 0 | 0 | 0 | ~8.2s |
| 5 | 50 | 50 | 0 | 0 | 0 | ~6.3s |
| 10 | 30 | 30 | 0 | 0 | 0 | ~5.6s |

**Total stress successes: 180 / 180**

## Level B — Architecture-critical batch

Files: m17_17, m17_14, m17_15, m17_9 concurrency, m17_22 gateway, FM-I1, FM-I1.5, FM-I2, FM-I3, FM-I4

| Collected/Passed | Failed | Skipped |
| --- | --- | --- |
| **293 passed** | 0 | 0 |

Duration ~52s

## Level B — Gateway / tool runtime (M49 + governance)

| Result |
| --- |
| **148 passed** |

## Level B — Local model harness

| Result |
| --- |
| FM-I6 + FM-I6.2 memory gate + m369 sample: **117 passed, 1 skipped** |

## Level B — TG sample

| Result |
| --- |
| m304 + m312 + m320: **119 passed** |

## Level C — Full backend suite

**Not claimed as full suite.** Architecture-critical and milestone samples run instead.  
Reason: full suite is multi-thousand tests and multi-hour class; host resources reserved for M17 concurrency proof + architecture gates.

Approximate architecture-critical + samples run this mission: **~700+ passed** (non-overlapping batches counted separately may double-count m17_17).

## Level D — Frontend

| Check | Result |
| --- | --- |
| `npm test` (after `npm install`) | **387 passed, 0 failed** |
| `npm run build` (next build) | **PASS** (production build completed) |
| Note | First full test run before install showed 8 spurious file-level failures; baseline tip without M17 showed the same pattern. After install: green. M17 did not touch frontend sources. |

## Level E — Browser

| Check | Result |
| --- | --- |
| Playwright package | present after npm install |
| Bounded browser suite | **NOT RUN** — requires live loopback platform server; out of safe zero-traffic default without starting services in this mission |
| Classification | ENVIRONMENT_LIMITED |

## Concurrency conclusion

M17 concurrent graph recovery is **validated** on this canonical tree (unit + multi-iteration + multi-worker stress).

## Level B — Private-alpha / agentdev / qualification sample

Files: m328, m336, m339, m345–m358, m369–m376

| Result | Duration |
| --- | --- |
| **1181 passed** | ~101s |

## Aggregate (non-overlapping primary batches)

| Batch | Passed |
| --- | --- |
| Architecture-critical (incl. m17_17 once) | 293 |
| Gateway/M49 | 148 |
| Local model FM-I6/I6.2 + sample | 117 (+1 skip) |
| TG m304/m312/m320 | 119 |
| Private-alpha / agentdev / m369–376 | 1181 |
| Frontend unit | 387 |
| M17 stress iterations | 180/180 |

Note: m17_17 is also inside architecture-critical batch. Full backend suite still **not** claimed.

