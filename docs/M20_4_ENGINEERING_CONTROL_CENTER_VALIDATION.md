# M20.4 Validation

## Commands

```bash
.venv/bin/python -m pytest tests/test_m20_4_engineering_control_center.py -q
.venv/bin/python -m pytest tests/test_m20_0_engineering_orchestrator.py -q
.venv/bin/python -m saathi.engineering control-center
.venv/bin/python -m saathi.control_center.cli engineering
.venv/bin/python -m saathi.engineering integrity
git diff --check
```

## Expected

- M20.4 tests green (mock-based)
- M20.0 regressions green
- Control Center facet returns schema_version engineering_status.v1
- Live Claude: environment-blocked if binary missing (dry_run path); no weak safeguards

## Not claimed

Production-ready autonomous engineering; live Claude network validation; full suite unless run.
