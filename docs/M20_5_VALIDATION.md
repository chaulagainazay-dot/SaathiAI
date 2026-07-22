# M20.5 Validation

## Commands

```bash
.venv/bin/python -m pytest tests/test_m20_5_session_ledger_recovery.py -q
.venv/bin/python -m pytest tests/test_m20_0_engineering_orchestrator.py tests/test_m20_4_engineering_control_center.py -q
```

## Expected

* M20.5 tests green  
* M20.0 / M20.4 regressions green  
* Ledger chain verifies  
* Recovery dry-run vs apply behaviour holds  

## Verdict target

`ENGINEERING SESSION LEDGER PILOT READY`
