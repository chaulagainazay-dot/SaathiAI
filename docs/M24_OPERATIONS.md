# M24 Operations

## CLI

```bash
python -m saathi.inference.provider_governance providers
python -m saathi.inference.provider_governance circuits
python -m saathi.inference.provider_governance costs
python -m saathi.inference.provider_governance readiness
python -m saathi.inference.provider_governance reservations
python -m saathi.inference.provider_governance recover-reservations
python -m saathi.inference.provider_governance reset-circuit <provider_id> --confirm
python -m saathi.inference.provider_governance force-open <provider_id> --confirm
python -m saathi.inference.provider_governance resolve-reservation <id> release --confirm
python -m saathi.inference.provider_governance resolve-reservation <id> settle --confirm --amount 0.01
```

Mutations require `--confirm`. Never prints secrets.

## Release / runtime

```bash
python -m saathi.inference.release_check
python -m saathi.inference.runtime_gate
```

## Budget day timezone

```bash
export SAATHI_BUDGET_DAY_TZ=UTC   # default
```

## Disable

* Kill all: existing `SAATHI_INFERENCE_KILL_ALL`
* Provider kill: existing provider kill env flags
* Cloud remains disabled unless explicit existing configuration

## Trading Guardian

UNCHANGED / UNENGAGED — no inference budget integration with trading limits.
