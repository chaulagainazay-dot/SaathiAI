# M20.7 Validation

## Commands

```bash
.venv/bin/python3 -m pytest tests/test_m20_7_console_consolidation.py -q
.venv/bin/python3 -m saathi.m20_console status
.venv/bin/python3 -m saathi.m20_console domains
.venv/bin/python3 -m pytest tests/test_m20_0_engineering_orchestrator.py tests/test_m20_6_live_local_certification.py -q
```

## Expected

* M20.7 tests green  
* Console schema `m20_console_status.v1`  
* `domains_isolated.merged_store == false`  
* TG engaged false  
* No generation/launch from console  

## Verdict

`M20.7 CONSOLIDATION READY` (observability only; not production adoption)
