# M25 Operations

## Commands

```bash
python -m saathi.inference.live_cert_m25 discover
python -m saathi.inference.live_cert_m25
python -m saathi.inference.provider_governance readiness
python -m saathi.inference.runtime_gate
python -m saathi.inference.release_check
# Package evidence (suite / secret scan / critical)
python -m saathi.inference.cert_evidence record-package --from-log /path/to/pytest.log
python -m saathi.inference.cert_evidence status
python -m saathi.inference.cert_evidence inject-for-gate
```

## Disable inference

Existing kill switches (unchanged):

```bash
export SAATHI_INFERENCE_KILL_ALL=1
```

## Trading Guardian

```text
UNCHANGED
UNENGAGED
LIVE TRADING NOT AUTHORIZED
```


## Evidence durability

```bash
ls docs/evidence/m25/
# LAST_SUCCESSFUL_LIVE_CERTIFICATION.json — preserved across blocked re-runs
# LATEST_ENVIRONMENT_OBSERVATION.json — current host snapshot
# LIVE_CERT_EVIDENCE.json — combined compatibility view
ls docs/evidence/m25/cert/
# full_suite_evidence.json, secret_scan_evidence.json, critical_check_evidence.json
```

A later low-memory observation does **not** erase a historical live PASS.
Package suite evidence is **not** invalidated by RAM drops (fingerprint is
code/policy/model only). Re-record package after material code/policy changes
or when artifacts are STALE (TTL 14 days).

Full operator flow: `docs/M25_PRODUCTION_CERTIFICATION.md`.
