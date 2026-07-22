# M20.3 — Validation Report

**Starting HEAD:** `f38ca66`  
**Branch:** `milestone/m7-security-engine`

## Commands and results

### 1–2. Repository + inventory

* Intake clean; `f38ca66` present; sync `0/0`  
* Inventory: `docs/M20_3_OPT_IN_LLM_CALLER_MIGRATION.md`

### 3–8. Focused tests

```bash
.venv/bin/python -m pytest tests/test_m20_3_opt_in_llm_caller_migration.py -q
# 34 passed
```

### 9–11. Regressions

```bash
.venv/bin/python -m pytest \
  tests/test_m20_3_opt_in_llm_caller_migration.py \
  tests/test_m20_2_governed_local_inference.py \
  tests/test_m20_1_openjarvis_inference.py \
  tests/test_llm_execution.py -q
# 97 passed
```

### 12–13. ModelRouter / ExecutionGateway

Covered by M20.2 suite included above (`test_model_gateway_uses_governed_path` etc.). Full gateway red-team suite not re-run this slice.

### 14–18. Format / lint / types / secrets / diff

* Secret scan: no secrets in new modules (compat events strip prompt/output)  
* `git diff --check` at commit time  
* Full monorepo lint/type suite: **not claimed**

### 19. Live small-model validation

```text
live=false label=unavailable error=ollama_unavailable
# honest: no live success claimed
```

See `docs/M20_3_LIVE_SMALL_MODEL_VALIDATION.md`.

### 20. Broader suite

Not claimed as full green for entire monorepo.

## Verdict

**`OPT-IN LOCAL INFERENCE ADOPTION READY`**

Pilot-ready only: default legacy, ≤2 callers, shadow + fallback + security denials tested, live Ollama not present on this host.
