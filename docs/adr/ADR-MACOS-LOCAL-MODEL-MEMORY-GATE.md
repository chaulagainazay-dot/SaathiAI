# ADR: macOS Local Model Memory Gate

| Field | Value |
| --- | --- |
| Status | **Accepted + implemented (FM-I6.2-MG-FIX)** — policy `fm_i6_2_mg_fix.combined_macos.v1` |
| Date | 2026-08-07 |
| Milestone | FM-I6.2-MG |
| Baseline | `54a4665e7bbc6e113c18ec50d150245934603991` |
| Decision code | `REPLACE_WITH_COMBINED_MACOS_GATE` |
| Supersedes (partially) | Informal “free% ≥ 20” language in FM-I5/I6 docs when interpreted as **pure free pages** |
| Related | ADR-LOCAL-MODEL-HARNESS, M370 `ResourceThresholds`, LocalModelHarness |

## Context

SaathiOS admits bounded local inference via `LocalModelHarness` against a
user-managed Ollama runtime on an **Apple Silicon 8 GiB** host. Live admission
must fail closed under memory pressure without owning Ollama processes or
unloading other workloads.

Operator and evidence language often stated:

> pure free RAM ≥ 20%

That criterion is **not** a valid primary safety gate on macOS and is **not**
what either M370 or the current harness probe actually measure.

## Decision

**Reject pure free pages ≥ 20% as a primary admission criterion.**

**Adopt a combined fail-closed macOS memory gate** (design accepted here;
source change is a separate authorized fix milestone).

## Traceability of the “20%” number

| Layer | What “free%” meant | Floor |
| --- | --- | --- |
| M370 `ResourceThresholds.min_free_memory_percent` | Darwin `memory_pressure` “System-wide memory free percentage” | **20** |
| M370 reclaimable floor | `vm_stat` free+inactive+speculative | **1024 MiB** |
| FM-I5 design §13 | “free% < 20 or available < 1024 MiB (M370 thresholds)” | copied heuristic |
| FM-I6 `MIN_FREE_MEMORY_PERCENT` / `MIN_AVAILABLE_MEMORY_MIB` | Constants 20 / 1024 | copied from M370 labels |
| FM-I6 `_default_memory_probe` | **`free_percent` = (free+inactive+speculative)/RAM×100** (misnamed) | both floors AND-ed |
| Operator / FM-I6.2 mission language | **pure free pages** | **not implemented** |

**Conclusion:** The 20% figure originated as a **conservative M370 host
heuristic** on an 8 GiB M2 under swap pressure, applied to **Darwin free%** and
paired with a reclaimable MiB floor. It was **not** a measured pure-free
threshold. FM-I6 implementation further diverged by reusing the name
`free_percent` for reclaimable ratio, without swap or model-budget checks.

## Metric definitions (authoritative for this ADR)

| Term | Definition | Source | Admission role |
| --- | --- | --- | --- |
| Pure free | `Pages free × page_size` | `vm_stat` | **Diagnostic only** — unsuitable as primary gate |
| Inactive | File-backed / cold pages reclaimable without necessarily swapping anonymous | `vm_stat` | Part of reclaimable |
| Speculative | Transient pages | `vm_stat` | Part of reclaimable |
| Purgeable | App-marked purgeable | `vm_stat` | Soft credit only; not hard headroom |
| Wired | Non-pageable | `vm_stat` | Not available |
| Active | Recently used | `vm_stat` | Not available |
| Compressor occupied | Memory held by compressor | `vm_stat` | Pressure signal |
| Reclaimable (SaathiOS) | free + inactive + speculative | calculated | Hard headroom input |
| Darwin free% | `memory_pressure` free percentage | OS | Hard coarse floor |
| Swap used / free | `sysctl vm.swapusage` | OS | Hard thrash signal |
| RSS | Process resident set | `ps` | Diagnostic / model load observation |
| Peak estimate | Conservative model memory budget | **estimate, not measurement** | Hard headroom input |

**Do not conflate free with available.** On macOS, pure free is often near zero
while the system is healthy.

## Combined gate (accepted design)

A live LocalModelHarness turn may be admitted only if **all** of the following
hold. Any probe failure → **fail closed**.

### G1 — Darwin free percentage

- Probe: `/usr/bin/memory_pressure` (or `-Q`)
- Require: `darwin_free_percent ≥ 20`
- Rationale: preserves M370 OS signal; not pure free

### G2 — Reclaimable absolute floor

- Probe: `vm_stat` + `hw.memsize`
- `reclaimable_mib = (free+inactive+speculative)*page_size / 1MiB`
- Require: `reclaimable_mib ≥ 2048`  
  (raises the M370 1024 MiB floor for live model load; 1024 alone is too low for 1.5B peaks)

### G3 — Model-budget headroom

- `required_mib = max(G2_floor, ceil(estimated_peak_mib × safety_factor))`
- For pinned `qwen2.5:1.5b` @ ctx 2048 / out 512 / one session:
  - weight file ≈ **940.4 MiB** (986 061 892 bytes / 1024²; Ollama list shows ~986 MB decimal)
  - conservative peak estimate ≈ **2681 MiB** (load ≈ 2.0× weight + KV ≈ 500 MiB + runtime ≈ 300 MiB)
  - safety factor **1.5** → **required ≈ 4022 MiB**
- Require: `reclaimable_mib ≥ required_mib`
- Estimates must be labeled **estimate**, never as measured peaks until a future measurement milestone records them.

### G4 — Swap bounds

- If swap total = 0 and used = 0: pass component
- If swap exists: require `used_mib ≤ 512` **and** no material growth in swapins across the sampling window
- Rapid swap growth → hard deny

### G5 — Compressor hard cap

- If `compressor_occupied / physical_ram ≥ 0.70` → hard deny
- If `≥ 0.50` → deny new model load (warning path maps to RESOURCE_PRESSURE)

### G6 — Concurrency / models

- `max_active_local_sessions == 1` (existing)
- `loaded_models ≤ 1` and if one loaded it must be the pin (existing policy retained)
- Parallel load forbidden

### Sampling and hysteresis

- Window: **5 s**, **2 samples**
- Admit only if both samples pass G1–G6
- After a deny, retry at most **2** times with **15 s** interval (operator/harness readiness refresh only — no process kill)
- Hysteresis: after a deny for headroom, require reclaimable ≥ required + **256 MiB** before next admit

### Failure disposition

| Breach | Readiness | Health |
| --- | --- | --- |
| Probe failure | `RESOURCE_PRESSURE` | DEGRADED / not ready |
| G1–G5 fail | `RESOURCE_PRESSURE` | DEGRADED |
| Second model / concurrency | `DEGRADED` / concurrency policy | DEGRADED |
| Critical Darwin free% (e.g. &lt; 5) or swap thrash | `RESOURCE_PRESSURE` | UNHEALTHY |

**No operator override** may bypass a critical pressure / thrash state.
Documentation-only “force live” flags remain forbidden for production.

### Audit fields (minimum)

```
darwin_free_percent, reclaimable_mib, required_reclaimable_mib,
estimated_peak_mib, safety_factor, swap_used_mib, swapins_delta,
compressor_occupied_mib, loaded_models, sample_count, gate_version
```

## Why not keep pure free ≥ 20%

Measured on the certifying host (idle Ollama, 0 swap, reclaimable ~2.2 GiB,
Darwin free% ~58%):

| Criterion | Result |
| --- | --- |
| Pure free ≥ 20% | **FAIL** (~0.7–0.8%) |
| Current harness reclaimable ≥ 20% and ≥ 1024 MiB | **PASS** |
| Proposed combined gate (model budget) | **FAIL** (~2.2 GiB &lt; 4.3 GiB required) |

Pure free would block a host that Darwin considers ~58% free. Conversely, the
current 1024 MiB floor can allow load when model peak estimates exceed
reclaimable headroom. Both errors are unacceptable.

## 8 GiB host suitability

**Not rejected.** `qwen2.5:1.5b` remains the pinned proof model. Live admission
on 8 GiB requires operator headroom (close heavy apps or restart) so that
**reclaimable ≥ required_mib**, not so that pure free reaches 20%.

## Consequences

### Positive

- Aligns names with measurements
- Fail-closed on insufficient **model** headroom, swap thrash, probe failure
- Keeps M370 Darwin free% floor as an OS signal
- Avoids pure-free false blocks

### Negative

- Combined gate is stricter than current 1024 MiB floor on busy 8 GiB hosts
- Peak estimates need eventual empirical calibration (future measurement only)

### Neutral

- FM-I6.2 live cert remains blocked until FM-I6.2-MG-FIX + host headroom
- FM-I7 remains blocked

## Implementation status

| Item | Status |
| --- | --- |
| This ADR | **Accepted design + implementation reference** |
| Evidence pack (design) | `docs/evidence/fm_i6_2_memory_gate/` |
| Implementation | `saathi/agent_runtime/harness/local_model_memory_gate.py` |
| Harness wire | `LocalModelHarness._run_memory_gate_unlocked` |
| Fix report | `docs/agent-runtime/FM_I6_2_MEMORY_GATE_FIX.md` |
| Fix evidence | `docs/evidence/fm_i6_2_memory_gate_fix/` |
| LocalModelHarness source change | **Done (FM-I6.2-MG-FIX)** |
| Live inference | **Not performed** |

## References

- `docs/agent-runtime/FM_I6_2_MEMORY_GATE_VALIDATION.md`
- `docs/agent-runtime/FM_I5_LOCAL_MODEL_HARNESS_DESIGN.md` §13
- `saathi/agentdev/model_inventory.py` (`ResourceThresholds`)
- `saathi/agentdev/host_probe.py`
- `saathi/agent_runtime/harness/local_model.py` (`_default_memory_probe`)
- `saathi/agent_runtime/harness/local_model_types.py` (`MIN_FREE_MEMORY_PERCENT`)
