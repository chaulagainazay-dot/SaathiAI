# M20.1 OpenJarvis Slice A — Validation

**Date:** 2026-07-16
**Canonical milestone:** M20.1 (not M18.3 — InsForge retains M18.3)
**Starting commit:** `f4065d681456f1603ce69ca02a5bdf7a00b6864b`
**Scope:** Selective inference primitives only
**Claims not made:** production-ready · live model benchmarks · NDJSON streaming · OJ process · Trading Guardian integration

## Numbering

| Label | Meaning |
|-------|---------|
| M18.3 | InsForge read-only pilot (historical, preserved) |
| M20.0 | Engineering Orchestrator track (separate, not this commit) |
| **M20.1** | OpenJarvis Slice A — this work |

## Commands executed (pre-commit revalidation)

```bash
cd /Users/macbookpro/SaathiAI
.venv/bin/python -m pytest tests/test_m20_1_openjarvis_inference.py -q
# → 26 passed
.venv/bin/python -m pytest tests/test_model_router.py tests/test_model_router_providers.py \
  tests/test_llm_execution.py tests/test_safety.py -q
# → 30 passed
.venv/bin/python -m pytest tests/test_m20_1_openjarvis_inference.py -q \
  -k 'trading or third_party or model_router_still or inference_package'
# → 4 passed
git diff --check
# → clean
# secret scan over intended Slice A paths → PASS
# ruff/black → unavailable in venv (not claimed)
```

### Live hardware probe (no model download)

`architecture=arm64`, `total_memory_gb=8.0`, available ~1.5 GB during probe, free disk ~72.7 GB, `downloads_performed=False`. Energy telemetry unsupported (honest). Unit tests do not require Ollama.

## Test coverage map

| Area | Tests |
|------|-------|
| Engine registration / discovery / fallback / timeout / stream / capabilities | `test_m20_1_openjarvis_inference.py` |
| Hardware M2 8GB / disk / no download | same |
| Catalogue provenance / stale / malformed | same |
| Router local-only / budget / advisory cannot override | same |
| Benchmarks schema / energy honesty / store | same |
| Skills licence / mounts / trading bypass | same |
| Config defaults safe | same |
| No trading imports in inference core | same |

## Classification of any failures

| Class | Meaning |
|-------|---------|
| introduced regression | new code broke green tests |
| pre-existing failure | failed on starting commit too |
| environment blocker | missing optional service (Ollama down) — unit tests mock transport |
| optional integration unavailable | live Ollama/cloud not required for Slice A |

## Resource notes (M2 8 GB)

- Unit tests: fake engines only — negligible memory.
- Live profiling: `profile_local_hardware()` — sysctl/vm_stat/disk only, **no model load**.
- Benchmarks: disabled by default; when enabled, single-engine sequential.
- Energy: **unsupported** (honest).

## Security

- Third-party skills default off.
- Forbidden permissions include trading and secrets surfaces.
- Sandbox policy rejects privileged + docker.sock + network-by-default.
- Cloud fallback default off; sensitive path uses `Privacy.LOCAL_ONLY`.

## Trading Guardian

- Unengaged.
- Blocking test: imported skill cannot request trading_connector / place_order.
- Inference package does not import trading modules.

## Rollback

See design doc. Flags off = idle package.
