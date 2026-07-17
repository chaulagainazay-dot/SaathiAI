# M25 Operations

## Commands

```bash
python -m saathi.inference.live_cert_m25 discover
python -m saathi.inference.live_cert_m25
python -m saathi.inference.provider_governance readiness
python -m saathi.inference.runtime_gate
python -m saathi.inference.release_check
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
```

A later low-memory observation does **not** erase a historical live PASS.
