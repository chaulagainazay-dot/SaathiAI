# M37 — Regression

## Required suites

```bash
.venv/bin/python -m pytest tests/test_m37_*.py -q
.venv/bin/python -m pytest tests/test_m31_credentials.py tests/test_m32_*.py \
  tests/test_m33_*.py tests/test_m34_*.py tests/test_m35_*.py tests/test_m36_*.py \
  tests/test_m37_*.py -q
.venv/bin/python -m pytest -q --tb=line
```

## Invariants preserved

- M31–M36 architecture reused, not replaced
- github_meta sole external provider
- rollout OFF; CANARY 0; ACTIVE 0
- no production credentials
- Trading Guardian unengaged
- M38 not started
