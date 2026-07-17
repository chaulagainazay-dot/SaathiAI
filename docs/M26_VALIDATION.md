# M26 Validation

## Focused

```bash
.venv/bin/python -m pytest tests/test_m26_inference_operations.py -q
.venv/bin/python -m pytest tests/test_m25_cert_evidence.py -q
.venv/bin/python -m pytest tests/test_m25_live_provider_certification.py -q
```

## Static

```bash
git diff --check
.venv/bin/python -m saathi.inference.release_check
.venv/bin/python -m saathi.inference.runtime_gate --json
```

## Full suite

```bash
.venv/bin/python -m pytest -q --tb=line
```

Do not run live inference concurrently with the full suite on 8 GB.

## Live smoke (only if memory allows)

```bash
ollama stop qwen2.5:1.5b   # free RAM after suite if needed
.venv/bin/python -m saathi.inference.live_cert_m25 discover
.venv/bin/python -m saathi.inference.ops status
.venv/bin/python -m saathi.inference.ops readiness
```

Live smoke must not overwrite historical PASS with a temporary environment failure
(dual-evidence model preserved).

## Acceptance snapshot

| Criterion | Expected |
|-----------|----------|
| Lifecycle CLI | present |
| Health ≠ readiness | distinct reports |
| Default mode | OFF |
| ACTIVE needs cert | yes |
| M25 memory rule | reused |
| Cloud fallback | disabled |
| Trading Guardian | unengaged |
| Suite | green |
