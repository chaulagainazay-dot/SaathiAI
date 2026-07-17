# M21.4 — Runtime Consolidation Audit

**Milestone:** Platform M21.4  
**Baseline HEAD:** `fa783ad` (M21.3 tip)  
**Authority module:** `saathi/inference/runtime_gate.py`

## Required result

```text
canonical authorities identified
duplicate critical authorities = 0
unclassified production gates = 0
```

## Canonical authorities

| Authority | Canonical file | Canonical symbol | Duplicate count | M21.4 action |
|-----------|----------------|------------------|-----------------|--------------|
| InferenceRequest contract | `saathi/inference/request.py` | `InferenceRequest` | 0 | VERIFY |
| Caller-policy registry | `saathi/inference/caller_policy.py` | `CallerPolicy` / `get_caller_policy` | 0 | VERIFY |
| Provider descriptor registry | `saathi/inference/provider_descriptor.py` | `ProviderDescriptor` / `get_descriptor` | 0 | VERIFY |
| Provider availability | `saathi/inference/availability.py` | `evaluate_availability` | 0 | VERIFY |
| Provider policy + kills | `saathi/inference/provider_policy.py` | `is_master_killed` / `is_provider_killed` | 0 | VERIFY |
| Cost policy | `saathi/inference/cost_policy.py` | `validate_pricing` | 0 | VERIFY |
| Failure taxonomy | `saathi/inference/failure_taxonomy.py` | `FailureClass` / `FailureType` | 0 | VERIFY |
| Retry / failover | `saathi/inference/provider_decision.py` | `decide_provider` path | 0 | VERIFY |
| Circuit breaker | `saathi/inference/circuit_breaker.py` | `ProviderCircuitBreakerRegistry` | 0 | VERIFY (process-local) |
| Residual path registry | `saathi/inference/residual_paths.py` | `RESIDUAL_PATH_CONTROLS` | 0 | VERIFY |
| Residual exception manifest | `docs/M21_3_RESIDUAL_EXCEPTION_MANIFEST.json` | `exceptions[]` | 0 | VALIDATE (count frozen ≤7) |
| Bypass guard | `saathi/inference/bypass_guard.py` | `scan_repository` | 0 | VERIFY |
| Release check | `saathi/inference/release_check.py` | `run_release_check` | 0 | INTEGRATE into ops release gate |
| Production config (settings) | `saathi/inference/prod_config.py` | `validate_production_config` | 0 | PRESERVE; consumed by gate |
| Production-configuration gate | `saathi/inference/runtime_gate.py` | `evaluate_runtime_gate` | 0 | **ADD** (consolidation only) |
| Production certification | `saathi/inference/runtime_gate.py` | `decide_production_certified` | 0 | **ADD** (always false without full evidence) |
| Legacy preflight | `saathi/inference/legacy_facade.py` | `preflight_inference` | 0 | VERIFY |

## Inventory summary

| Area | Location | Notes |
|------|----------|-------|
| M21 runtime modules | `saathi/inference/*` | M20.1–M21.3 stack intact |
| Production-config modules | `prod_config.py` + `runtime_gate.py` | Settings vs readiness gate split |
| Release-check modules | `release_check.py` + `ops/release_gate.py` | Inference check blocking canonical gate |
| Critical-check integration | `saathi/repair/critical_checks.json` | `m21.4.*` entries |
| Path / caller / provider registries | residual_paths, caller_policy, provider_descriptor | Single each |
| Kill switches | `provider_policy.KILL_ALL_ENV` + per-family | Matrix tested |
| Circuit / cost state | process-local | Documented limitation (M24 target) |
| Console surfaces | `m20_console` + `runtime-readiness` | Read-only |
| Test suites | `tests/test_m21_*.py`, `tests/test_m20_*.py` | Focused + full suite |
| Production certification | always `false` unless all mandatory gates PASS | Live provider env-blocked |

## Shadow / compatibility facades (not competing authorities)

* `saathi/llm.generate` — deprecated preflight facade (M22 expiry)
* `saathi/inference/compat.py` — cheap_ask / prose_clean adoption
* `saathi/inference/chat_adapter.py` — chat compatibility wrapper
* M13.5 `ops/release_gate.py` — broader ops gate; now **calls** inference release check (not a second architecture scanner)

## M21.4 actions completed

1. Added consolidated `runtime_gate` without creating parallel registries  
2. Integrated inference `release_check` into `ops.release_gate.release_check`  
3. Validated residual exception manifest fields and frozen count  
4. Added critical-check IDs for M21.4  
5. Extended M20 console with `runtime-readiness`  
6. Proved `production_certified=false` under partial evidence  
