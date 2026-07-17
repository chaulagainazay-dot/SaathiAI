# M28 Validation

```bash
cd /Users/macbookpro/SaathiAI

.venv/bin/python -m pytest tests/test_m28_connector_migration.py -q
.venv/bin/python -m pytest tests/test_m27_connector_framework.py -q
.venv/bin/python -m pytest tests/test_m26_inference_operations.py -q
.venv/bin/python -m pytest tests/test_m25_cert_evidence.py -q

.venv/bin/python -m saathi.connectors.gov.bypass_guard
.venv/bin/python -m saathi.inference.release_check
.venv/bin/python -m saathi.inference.runtime_gate --json

.venv/bin/python -m pytest -q --tb=line
```

## Acceptance

| Criterion | Expected |
|-----------|----------|
| Canonical path | Gateway → gov runtime |
| Production bypasses | 0 |
| Default mode | OFF |
| SHADOW | no side effects |
| CANARY | deterministic |
| FINANCIAL/TRADING | blocked |
| production_certified | true (computed) |
| Trading Guardian | unengaged |
