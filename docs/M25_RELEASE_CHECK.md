# M25 Release Check

Existing release-check remains authoritative for architecture (M22–M24 rules).

M25 adds runtime-gate checks:

* `m25_live_provider_cert` — PASS only with live certification evidence  
* `m25_no_mock_as_live` — live flag consistent with certification claim  
* `m25_production_cert_invariant` — production_certified requires live  

```bash
python -m saathi.inference.release_check
python -m saathi.inference.runtime_gate
```
