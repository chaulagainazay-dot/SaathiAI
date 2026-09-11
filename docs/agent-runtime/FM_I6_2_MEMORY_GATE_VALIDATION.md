# FM-I6.2-MG — macOS Memory-Gate Validation for LocalModelHarness

| Field | Value |
| --- | --- |
| Milestone | **FM-I6.2-MG** |
| Mode | Validation and design only |
| Branch | `hardening/fm-i6.2-ollama-live-certification` |
| Baseline SHA | `54a4665e7bbc6e113c18ec50d150245934603991` |
| Date | 2026-08-07 |
| Terminal verdict | `FM_I6_2_MEMORY_GATE_REQUIRES_REVISION` |
| Decision | `REPLACE_WITH_COMBINED_MACOS_GATE` |
| Live inference | **None** |
| Production certified | **False** |
| FM-I7 ready | **No** |

## 1. Integrity statement

- Baseline branch and SHA verified before work.
- Working tree started clean at `54a4665`.
- No Ollama start/stop/restart, no model load, no model pull, no inference.
- No firewall, LaunchAgent, or host configuration changes.
- No process kills.
- Documentation and evidence only; no harness source change in this milestone.

## 2. Origin of the current “20% free” gate

### Explicit design statements

| Source | Statement |
| --- | --- |
| FM-I5 design §13 | Fail closed if free% &lt; 20 or available &lt; 1024 MiB **(M370 thresholds)** |
| FM-I6.1 operator guide | Free memory percentage ≥ 20% and available ≥ 1024 MiB |
| FM-I6 constants | `MIN_FREE_MEMORY_PERCENT = 20`, `MIN_AVAILABLE_MEMORY_MIB = 1024.0` |
| M370 `ResourceThresholds` | `min_free_memory_percent: 20` against **`memory_pressure` free%**; `min_available_memory_mib: 1024` against **reclaimable** pages |

### Implementation (authoritative code)

`saathi/agent_runtime/harness/local_model.py::_default_memory_probe`:

```text
available = (Pages free + Pages inactive + Pages speculative) * page_size
free_percent = available / total_ram * 100
ok = free_percent >= 20 AND available_mib >= 1024
```

**Critical findings:**

1. Harness `free_percent` is **reclaimable ratio**, not pure free pages.
2. Harness does **not** call `memory_pressure` (unlike M370).
3. Harness does **not** check swap, compressor trend, or model peak budget.
4. Operator language “pure free ≥ 20%” matches **neither** M370 nor harness code.
5. The 20% figure is a **conservative design heuristic** for 8 GiB M2 hosts (M370 rationale), not a measured pure-free safety boundary.

## 3. Current host metrics (measured)

See `docs/evidence/fm_i6_2_memory_gate/MEMORY_METRICS.json`.

Summary (two samples, Ollama idle, no model loaded, swap 0):

| Metric | Sample range | Kind |
| --- | --- | --- |
| Physical RAM | 8.0 GiB | measured |
| Pure free % | **0.73–0.80%** | calculated |
| Reclaimable % (free+inactive+spec) | **~27.4–27.5%** | calculated (= harness free_percent) |
| Reclaimable MiB | **~2247–2252** | calculated |
| Darwin `memory_pressure` free % | **58%** | measured |
| Swap used | **0** | measured |
| Compressor occupied | **~1.90 GiB** | measured |
| Ollama RSS | **~22 MiB** | measured |
| Pure free ≥ 20% | **FAIL** | — |
| Current harness gate | **PASS** | — |
| Proposed combined gate | **FAIL** (headroom &lt; model budget) | — |

**Observation:** Pure free stayed well below 20% while Darwin free%, reclaimable memory, and swap indicated a stable idle system. Pure free is not a stable admission primary metric.

## 4. Metric definitions

Documented fully in `docs/adr/ADR-MACOS-LOCAL-MODEL-MEMORY-GATE.md`.

Suitable for admission control:

- Darwin free% (coarse OS)
- Reclaimable MiB (headroom upper bound)
- Swap used / swap activity
- Loaded model count / single session
- Model budget estimate × safety factor (labeled estimate)

Unsuitable as primary:

- Pure free % on macOS with healthy file cache
- Full credit of compressed pages as “available”
- Available MiB without model budget comparison

## 5. Candidate comparison

See `GATE_COMPARISON.json`. Result: **combined gate** only.

## 6. qwen2.5:1.5b memory budget (estimate, not measured peak)

| Component | Value | Kind |
| --- | --- | --- |
| Weight file | 986,061,892 bytes (**940.4 MiB** binary; ~986 MB decimal) | inventory measured |
| Load footprint (optimistic) | ~1.2× weight | estimate |
| Load footprint (conservative) | ~2.0× weight | estimate |
| KV / context @ 2048 | ~300–800 MiB | estimate range |
| Runtime overhead | ~300 MiB | estimate |
| **Conservative peak** | **~2681 MiB** | estimate |
| Safety factor | 1.5 | design |
| **Required reclaimable** | **~4022 MiB** | calculated from estimate |
| Uncertainty | ±30% until empirical load measurement milestone | limitation |

Pinned config constraints: ctx 2048, out ≤ 512, one session, no second model, synthetic short prompt, streaming — all reduce but do not eliminate load cost.

## 7. False-block analysis (selected scenarios)

| Scenario | Pure free ≥ 20% | Current harness | Combined (proposed) |
| --- | --- | --- | --- |
| Low pure free, high inactive, Darwin free% high, swap 0 | false block | may pass | headroom decides |
| After large disk cache / indexing | false block | may pass | headroom decides |
| Immediately after reboot (high pure free) | pass | pass | still requires model budget |
| Current host idle with browsers | false block | pass | **deny** (insufficient model headroom) |

## 8. False-allow analysis

| Scenario | Pure free ≥ 20% | Current harness (1024 MiB) | Combined |
| --- | --- | --- | --- |
| Reclaimable 1.1 GiB, model needs ~2.8 GiB peak | n/a | **false allow** | deny |
| Rising swap, free% still high | may allow | allows | deny |
| Second model already loaded | n/a | inventory policy | deny |
| Probe failure | depends | fail closed on exception | fail closed |
| Compressor thrash | ignored | ignored | deny at hard cap |

## 9. Selected decision

**`REPLACE_WITH_COMBINED_MACOS_GATE`**

Not selected: keep pure free 20%; pressure-only; available-only; reject 8 GiB path; “more evidence” as sole outcome (evidence is sufficient to reject pure free primary and to specify a combined design).

## 10. Exact proposed thresholds

| Component | Threshold |
| --- | --- |
| Darwin free% min | **20** |
| Reclaimable absolute floor | **2048 MiB** |
| qwen2.5:1.5b required reclaimable | **max(2048, 2681×1.5) ≈ 4022 MiB** |
| Swap used max | **512 MiB** with no rising swapins in window |
| Compressor hard | **≥ 70% of RAM** deny |
| Compressor soft | **≥ 50% of RAM** deny new load |
| Loaded models | **≤ 1** and must match pin if loaded |
| Active local sessions | **1** |

Thresholds are **not** chosen merely so the current host passes. On the current host the proposed gate **denies** admission.

## 11. Sampling and hysteresis

- 2 samples over 5 seconds; both must pass
- Up to 2 readiness retries, 15 s apart
- After headroom deny: require reclaimable ≥ required + 256 MiB

## 12. Failure disposition and health mapping

See ADR. Critical pressure / thrash → no operator override path for production.

## 13. Test plan (injected probes; no live Ollama required)

| # | Scenario | Expect |
| --- | --- | --- |
| T1 | Normal Darwin free%, reclaimable ≥ required | admit |
| T2 | Normal free%, reclaimable &lt; required | RESOURCE_PRESSURE |
| T3 | Darwin free% &lt; 20 | RESOURCE_PRESSURE |
| T4 | Darwin free% critical (&lt; 5) | RESOURCE_PRESSURE / unhealthy |
| T5 | Swap used 0 | pass component |
| T6 | Swap used 200 MiB stable | pass if ≤ 512 |
| T7 | Swap used 800 MiB or rising swapins | deny |
| T8 | High inactive, pure free &lt; 1%, reclaimable OK + budget OK | admit |
| T9 | Model already loaded = pin | allow if headroom still OK |
| T10 | Second model loaded | deny |
| T11 | Concurrent session active | deny (session ceiling) |
| T12 | Memory probe exception | fail closed |
| T13 | Stale sample / single sample only | deny (need window) |
| T14 | Negative / impossible metrics | fail closed |
| T15 | Edge: reclaimable == required | deny (strict ≥ with hysteresis after fail) |
| T16 | Hysteresis: prior deny, reclaimable == required | still deny until +256 MiB |
| T17 | Repeated admission while metrics stable pass | admit |
| T18 | Compressor occupied ≥ 70% RAM | deny |

Implement in FM-I6.2-MG-FIX via injectable `memory_probe` (already supported).

## 14. Source-change decision

**No production code change in FM-I6.2-MG.**

Reasons:

- Replacement is evidence-backed but multi-component
- Prefer separate narrow FM-I6.2-MG-FIX with unit tests
- Avoid coupling gate rewrite with live certification

Current source continues to enforce the **misnamed reclaimable 20% + 1024 MiB** gate until fix lands. Live cert must document both the known limitation and the accepted target gate.

## 15. Documentation updates

| Artifact | Action |
| --- | --- |
| `docs/adr/ADR-MACOS-LOCAL-MODEL-MEMORY-GATE.md` | Created |
| `docs/agent-runtime/FM_I6_2_MEMORY_GATE_VALIDATION.md` | Created (this file) |
| `docs/evidence/fm_i6_2_memory_gate/*` | Created |
| `docs/AUTONOMOUS_ROADMAP.md` | FM-I6.2-MG section |
| FM-I5 / FM-I6.1 / FM-I6.2 notes | Clarification pointers |

## 16. Production and live readiness

| Gate | Status |
| --- | --- |
| Production certified | **False** |
| FM-I6.2 live certification | **Blocked** (binding remediated on host; memory gate design revision + headroom pending) |
| FM-I7 | **Blocked** |

## 17. Explicit non-actions

- No live inference
- No Ollama process control
- No model download
- No threshold relaxation to force pass
- No pure-free redefinition as “success”
- No FM-I7 start

## 18. Recommended next step

1. **FM-I6.2-MG-FIX** (separate auth): implement combined gate + injected-probe tests; rename metrics; wire Darwin free% + swap + model budget.
2. Operator creates headroom (close heavy apps / controlled restart, Ollama.app closed) until reclaimable ≥ required.
3. Resume FM-I6.2 live certification only after MG-FIX lands **or** an explicit temporary dual-recording of current gate vs target gate is authorized.

## 19. Stop statement

**STOP after FM-I6.2-MG.** Do not resume live inference automatically. Do not begin FM-I7.
