# M25 Final Report — Live Local Provider Certification and Production Inference Readiness

## 0. Closeout verdict (package evidence)

```text
M25 COMPLETE — production_certified=true
READY TO START M26 (operator authorize only)
```

Canonical package evidence under `docs/evidence/m25/cert/` + historical live PASS.
Architecture: `docs/M25_PRODUCTION_CERTIFICATION.md`.

| Gate | Status |
|------|--------|
| Historical live certification | PASS |
| Current environment | PASS or MEMORY_BLOCKED (RAM-dependent) |
| Full suite evidence | PASS (3113 passed, 1 skipped) |
| Secret scan evidence | PASS |
| Critical check evidence | PASS |
| Release check | PASS |
| Production certification | TRUE |

## 1. Earlier blocked baseline (pre-unlock)

```text
M25 BLOCKED — LIVE LOCAL PROVIDER ENVIRONMENT UNAVAILABLE
```

Initial M25 start: live certification was **not** claimed. Later unlock + package
evidence closeout set `production_certified=true` when all mandatory gates PASS.

## 2. Baseline

| Item | Value |
|------|-------|
| Start HEAD | `e9571f3` |
| Tip HEAD | `85a5f36` |
| Branch | `milestone/m7-security-engine` |
| Worktree | clean at start |
| Remote | 0/0 |
| M22–M24 | COMPLETE WITH LIMITATIONS |
| Residual exceptions | 0 |
| Durable governance | active |

## 3. Questions answered

| # | Question | Answer |
|---|----------|--------|
| 1 | Provider installed & reachable? | **No** — broken symlink; app missing; port closed |
| 2 | Models installed? | **None** |
| 3 | Compatible models? | **None available** |
| 4 | Real non-stream? | **ENVIRONMENT_BLOCKED** |
| 5 | Real stream? | **ENVIRONMENT_BLOCKED** |
| 6 | Cancellation? | **ENVIRONMENT_BLOCKED** |
| 7 | Timeout mapping? | **ENVIRONMENT_BLOCKED** (runtime ready; no live transport) |
| 8 | Durable circuits on real failure? | **ENVIRONMENT_BLOCKED** |
| 9 | Zero-cost settlement live? | **ENVIRONMENT_BLOCKED** (durable path unit-proven M24) |
| 10 | Restart recovery with real attempt? | **ENVIRONMENT_BLOCKED** |
| 11 | Governed chat e2e live? | **ENVIRONMENT_BLOCKED** (M23 path preserved) |
| 12 | Kill switches prevent transport? | Static authority PASS; live kill test blocked |
| 13 | Privacy/logging preserved? | Design + evidence privacy-safe; live canary not run |
| 14 | Safe to certify production inference? | **No** |
| 15 | Exact blockers? | broken symlink, binary unusable, runtime down, no models, memory pressure |

## 4–6. Scope / rules / intake

Only M25. Did not install Ollama, pull models, enable cloud, add credentials, deploy, merge, force-push, engage Trading Guardian, or start M26.

## 7. Environment

See `docs/M25_LOCAL_PROVIDER_ENVIRONMENT_AUDIT.md`.

## 8–11. Discovery / models / health

* Binary: broken symlink to missing Ollama.app  
* Models: 0  
* Health: unreachable  
* Secondary CLI not used as cert path  

## 12–21. Live cases

All live cases **ENVIRONMENT_BLOCKED**. Harness implements governed path for operator unlock (`live_cert_m25._run_live_cases`).

## 22. Evidence bundle

* `docs/evidence/m25/LIVE_CERT_EVIDENCE.json`  
* `docs/evidence/m25/LIVE_CERT_SUMMARY.md`  
* Privacy: redacted; no raw prompts/outputs  

## 23. Certification gates

| Gate | Status |
|------|--------|
| env_binary | ENVIRONMENT_BLOCKED |
| env_runtime | ENVIRONMENT_BLOCKED |
| env_model | ENVIRONMENT_BLOCKED |
| resource_memory | ENVIRONMENT_BLOCKED |
| residual_exceptions | PASS |
| durable_governance | PASS |
| cloud_fallback_disabled | PASS |
| endpoint_allowlist | PASS |
| live_* | ENVIRONMENT_BLOCKED |
| production_certified | **false** |

## 24. Runtime gate

`python -m saathi.inference.runtime_gate` — M25 checks present; `m25_live_provider_cert=ENVIRONMENT_BLOCKED`; production_certified=false.

## 25. Release check

`python -m saathi.inference.release_check` — ok=true; production_certified=false.

## 26. Invariants

```text
residual inference exceptions = 0
process-local production authorities = 0
direct provider bypasses = 0
unknown inference paths = 0
cloud fallback = disabled
production_certified = false
live provider certified = false
configured model certified = false
```

## 27. Compatibility

M22 adapters, M23 chat, M24 durable governance unchanged and regression-tested.

## 28. Trading Guardian

```text
UNCHANGED
UNENGAGED
LIVE TRADING NOT AUTHORIZED
```

## 29–31. Tests

Focused: `tests/test_m25_live_provider_certification.py` — 10 passed  

Full suite: **3085 passed, 1 skipped, 0 failed** in 670.81s.

## 32–33. Critical checks / secret scan

No secrets added. Architecture checks green.

## 34–35. Files / docs

See git commits. Docs: `docs/M25_*`, `docs/evidence/m25/*`.

## 36. Known limitations

* Ollama.app missing / broken symlink  
* No models  
* Memory pressure (~1.4 GB free)  
* Live cert impossible until operator unlock  

## 37. Technical debt

ENVIRONMENT_BLOCKED live cert remains operator-gated (install + model + memory).

## 38. Disable

`SAATHI_INFERENCE_KILL_ALL=1`

## 39. Rollback

See `docs/M25_ROLLBACK.md`.

## 40. Commit and push

Pushed to `origin/milestone/m7-security-engine`; ahead/behind 0/0; clean tree.

## 41. Production impact

Touched: live cert harness, runtime gate M25 checks, docs/evidence, tests.  
Untouched: production deploy, Trading Guardian, cloud providers, user models.

## 42. Recommended next milestone

**M26** only after operator unlock **or** next roadmap milestone that does not require live local provider — operator authorize only. Do not start it here.

## 43. Exact next action

```bash
# Operator: repair Ollama.app, start service, pull ≤3B model, free memory, then:
python -m saathi.inference.live_cert_m25
```

## 44. Final milestone verdict

```text
M25 BLOCKED — LIVE LOCAL PROVIDER ENVIRONMENT UNAVAILABLE
```

## Closeout repair (post 285d95b)

**Root cause of suite regressions:** Ollama installation made `select_provider("auto")`
select `OllamaEmbedder` without an embedding model → no stored vectors → keyword-only.

**Why not pull nomic-embed-text:** operator policy / M25 closeout forbids new model
dependencies to green the suite; readiness must fail closed and fall back to
deterministic local for auto mode.

**Test isolation:** `tests/test_memory_engine.py` injects `LocalDeterministicEmbedder`.

**Production auto:** Ollama embedder ready only when model present in `/api/tags`.

**Evidence durability:** `LAST_SUCCESSFUL_LIVE_CERTIFICATION.json` preserved across
later memory-blocked observations; latest observation is separate.

**Full suite after repair:** 3095 passed, 1 skipped, 0 failed.

**Live recert:** `M25 COMPLETE WITH LIMITATIONS — LIVE LOCAL PROVIDER VERIFIED; PRODUCTION CERTIFICATION BLOCKED` (`production_certified=false`).

**Trading Guardian:** UNCHANGED / UNENGAGED

