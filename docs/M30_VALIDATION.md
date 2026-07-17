# M30 — Validation

## Focused

```bash
.venv/bin/python -m pytest tests/test_m30_connector_conformance.py -q
.venv/bin/python -m pytest tests/test_m29_connector_identity.py tests/test_m28_connector_migration.py tests/test_m27_connector_framework.py tests/test_m26_inference_operations.py -q
```

## Conformance

```bash
python -m saathi.connectors.conformance assess-all
python -m saathi.connectors.conformance verify
python -m saathi.connectors.conformance drift
python -m saathi.connectors.gov.bypass_guard
```

## Canonical gates

```bash
python -m saathi.inference.release_check
python -m saathi.inference.runtime_gate
```

## Full suite

```bash
.venv/bin/python -m pytest -q --tb=line
```
