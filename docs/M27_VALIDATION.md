# M27 Validation

```bash
.venv/bin/python -m pytest tests/test_m27_connector_framework.py -q
.venv/bin/python -m pytest tests/test_m26_inference_operations.py -q
.venv/bin/python -m saathi.inference.release_check
.venv/bin/python -m saathi.inference.runtime_gate --json
.venv/bin/python -m pytest -q --tb=line
```

## Acceptance

| Criterion | Expected |
|-----------|----------|
| Lifecycle states | deterministic |
| Default mode | OFF |
| ACTIVE needs cert | yes |
| HTTP methods | governed |
| MCP/browser | reuse existing |
| Local tools | allowlist only |
| Secrets in evidence | none |
| production_certified | preserved true |
| Trading Guardian | unengaged |
