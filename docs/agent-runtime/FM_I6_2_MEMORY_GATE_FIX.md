# FM-I6.2-MG-FIX — Combined macOS Memory Gate Implementation

| Field | Value |
| --- | --- |
| Milestone | **FM-I6.2-MG-FIX** |
| Branch | `hardening/fm-i6.2-macos-memory-gate-fix` |
| Baseline | `54a4665e7bbc6e113c18ec50d150245934603991` |
| Decision | `REPLACE_WITH_COMBINED_MACOS_GATE` |
| Policy version | `fm_i6_2_mg_fix.combined_macos.v1` |
| Live inference | **None** |
| Production certified | **False** |
| Terminal verdict | `FM_I6_2_COMBINED_MEMORY_GATE_CERTIFIED_WITH_LIMITATIONS` |

## Old gate behavior

`_default_memory_probe` computed:

```text
reclaimable = (Pages free + inactive + speculative) * page_size
free_percent = reclaimable / RAM * 100   # misnamed
ok = free_percent >= 20 AND reclaimable_mib >= 1024
```

Missing: Darwin `memory_pressure` free%, model headroom, swap trend, compressor limits, two-sample window, hysteresis, loaded-model checks in the probe itself.

## New combined gate

Module: `saathi/agent_runtime/harness/local_model_memory_gate.py`

Wired via `LocalModelHarness._run_memory_gate_unlocked` when `enforce_memory_gate=True`.

| Condition | Threshold |
| --- | --- |
| Darwin free% | ≥ 20 |
| Absolute reclaimable | ≥ 2048 MiB |
| Model headroom | ≥ max(2048, 2681 × 1.5) ≈ **4021.5 MiB** for pin |
| Swap used | ≤ 512 MiB |
| Swap rising across samples | deny |
| Compressor soft | ≥ 50% of RAM deny |
| Compressor hard | ≥ 70% of RAM deny |
| Loaded models | ≤ 1 and must be pin if present |
| Active sessions (new admit) | &lt; 1 when max_concurrency=1 |
| Samples | 2 within ~5 s window; both must pass |
| Hysteresis after deny | required + 256 MiB |
| Max retries | 2 (explicit re-admit only) |
| Probe failure | fail closed |

**Pure free** is diagnostic telemetry only (`pure_free_bytes` / `pure_free_percent`).

## Model budget (estimate)

| Field | Value |
| --- | --- |
| Model | `qwen2.5:1.5b` |
| Digest | `65ec06548149b04c096a120e4a6da9d4017ea809c91734ea5631e89f96ddc57b` |
| Weight | ~940.4 MiB (from size_bytes) |
| Estimated peak | **2681 MiB** (estimate, not measured) |
| Safety factor | 1.5 |
| Required headroom | **~4021.5 MiB** |

## Compatibility

- Legacy `memory_probe: Callable[[], MemorySnapshot]` still works for simple ok/deny tests.
- Prefer `memory_gate: CombinedMacOSMemoryGate` with `fixed_samples` or real Darwin sampler.
- `MIN_AVAILABLE_MEMORY_MIB` raised to **2048** for absolute floor alignment; primary model headroom is stricter.

## Tests

`tests/test_fm_i6_2_memory_gate_fix.py` — injected scenarios T1–T30 + budget/parser tests.

Regression: FM-I1, I1.5, I2, I3, I4, I6 + MG-FIX → see evidence JSON.

## Live certification

Still **separately gated**. This milestone does not run live inference. Host must still satisfy combined headroom (~4 GiB reclaimable) before live cert.

## FM-I7

**Blocked.**
