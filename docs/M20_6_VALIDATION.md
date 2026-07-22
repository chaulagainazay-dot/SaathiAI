# M20.6 Validation

**Starting HEAD:** `fb7eaea`  
**Host:** Apple M2 8 GB  

## Commands

```bash
.venv/bin/python3 -m pytest tests/test_m20_6_live_local_certification.py -q
.venv/bin/python3 -m saathi.inference.certification discover
.venv/bin/python3 -m saathi.inference.certification run
.venv/bin/python3 -m pytest tests/test_m20_2_governed_local_inference.py tests/test_m20_3_opt_in_llm_caller_migration.py -q
```

## Live result (this host)

```text
status: BLOCKED
verdict: M20.6 BLOCKED — NO APPROVED INSTALLED SMALL MODEL OR LIVE LOCAL ENGINE AVAILABLE
```

Evidence: broken/missing Ollama binary, zero installed models, ~1.3 GB free RAM.

## Deterministic suite

Injected governed path quality corpus: critical_fails=0, adherence met (tests).

## Not claimed

Live generation success · model download · global adoption · cloud calls · TG engagement
