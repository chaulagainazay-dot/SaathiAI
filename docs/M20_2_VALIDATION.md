# M20.2 Validation

**Canonical milestone:** M20.2 — Governed Local Inference Execution Path
**Starting HEAD (pre-commit):** see git history relative to M20.1 `cf83ced`
**Live generation:** not claimed (unit tests use FakeEngine)

## Commands

```bash
.venv/bin/python -m pytest tests/test_m20_2_governed_local_inference.py -q
# → 32 passed

.venv/bin/python -m pytest tests/test_m20_1_openjarvis_inference.py \
  tests/test_m20_2_governed_local_inference.py -q
# → 58 passed

.venv/bin/python -m pytest tests/test_model_router.py \
  tests/test_model_router_providers.py tests/test_llm_execution.py \
  tests/test_safety.py -q
# → 30 passed

.venv/bin/python -m pytest tests/test_m17_22_execution_gateway.py -q
# → 25 passed
```

## Hardware probe (no model load)

arm64, 8 GB total, available memory pressure may warn; `downloads_performed=False`.
Energy unsupported.

## Secret scan

Run over changed paths before commit (strong patterns).

## Defaults

`enabled=False`, `gateway_enabled=False`, `allow_cloud_fallback=False`.
