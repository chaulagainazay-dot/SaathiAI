# FM-I6.2-LIVE — Live Certification Attempt (Memory Gate Denied)

| Field | Value |
| --- | --- |
| Milestone | **FM-I6.2-LIVE** |
| Date | 2026-08-07 |
| Branch | `hardening/fm-i6.2-macos-memory-gate-fix` |
| Baseline SHA | `a83305f0b1e69db896fc6b86f0d4ddbc10f92e82` |
| Terminal verdict | **`FM_I6_2_LIVE_MEMORY_GATE_DENIED`** |
| Production certified | **False** |
| Model role-qualified | **False** |
| Live inference | **Not run** |
| FM-I7 ready | **No** |

## Publication

| Item | Status |
| --- | --- |
| Push MG-FIX | **Done** — `origin/hardening/fm-i6.2-macos-memory-gate-fix` @ `a83305f` |
| Parent base pushed | `origin/hardening/fm-i6.2-ollama-live-certification` @ `54a4665` (required for PR base) |
| Draft PR | **https://github.com/chaulagainazay-dot/SaathiAI/pull/22** |
| PR #21 rewrite | **Not done** |

## Runtime boundary

| Check | Result |
| --- | --- |
| Firewall | Enabled (State = 1) |
| Ollama processes | One: pid 983, user macbookpro |
| Bind | `127.0.0.1:11434` only |
| Wildcard | **No** |
| Server version | **0.32.5** |
| Client CLI | 0.32.6 (warning only) |
| Model pin | `qwen2.5:1.5b` |
| Digest | Exact match `65ec06548149b04c096a120e4a6da9d4017ea809c91734ea5631e89f96ddc57b` |
| Loaded models | Empty |

## Combined memory gate (policy `fm_i6_2_mg_fix.combined_macos.v1`)

| Sample | Darwin free% | Reclaimable MiB | Pure free MiB | Compressor% | Swap MiB |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 | 58 | 2380.34 | 55.47 | 23.27 | 0 |
| 2 | 58 | 2394.94 | 76.08 | 23.25 | 0 |

| Decision | Value |
| --- | --- |
| Allowed | **False** |
| Reason | **`MODEL_HEADROOM_LOW`** |
| Required headroom | **4021.5 MiB** |
| Available (min of samples) | **2380.34 MiB** |
| Deficit | **1641.16 MiB** |

Other hard conditions (Darwin free%, absolute 2048 floor, swap, compressor soft/hard, model count, sessions, probe validity) **passed**. Only model-headroom failed.

**No inference was attempted.** Thresholds were not relaxed.

## Live tests A/B/C

| Test | Status |
| --- | --- |
| A Structured streaming | **NOT_RUN** |
| B Tool-like prose | **NOT_RUN** |
| C Cancellation | **SKIPPED** |

## Empirical budget classification

**`LIVE_TEST_NOT_RUN`**

No peak measurement under load. Pre-admission reclaimable ~2.38 GiB on 8 GiB host is insufficient vs design required ~4.02 GiB.

## Operator path to re-attempt

1. Close memory-heavy apps (e.g. browsers) or restart Mac with Ollama.app closed.
2. Confirm loopback-only bind + firewall still OK.
3. Re-evaluate dual-sample gate until reclaimable ≥ **4021.5 MiB** (or ≥ **4277.5 MiB** if hysteresis applies after prior denial).
4. Re-authorize a new FM-I6.2-LIVE run — do **not** lower thresholds.

## Evidence pack

`docs/evidence/fm_i6_2_live/`

## Explicit non-actions

- No model load / inference  
- No threshold change  
- No Ollama process control  
- No FM-I7  
- No role qualification  
- No production certification  

## Stop

**STOP after FM-I6.2-LIVE** with verdict `FM_I6_2_LIVE_MEMORY_GATE_DENIED`.
