# M44 — Operator Guide

> **M44 authorizes nothing to run.** A `VALIDATED` verdict is advisory: it says a
> request is well-formed, bounded, and evidence-backed. Executing any rollout
> requires a **completely separate operator authorization** outside M44.

## CLI commands

All commands print the non-production banner first, then JSON.

```
python -m saathi.credentials.cli m44-status            # framework readiness (advisory)
python -m saathi.credentials.cli m44-list-policies      # policies + ceilings + fingerprints
python -m saathi.credentials.cli m44-simulate --policy Simulation
python -m saathi.credentials.cli m44-create-rollout  --request-file REQ.json [--persist]
python -m saathi.credentials.cli m44-review-rollout  --request-file REQ.json [--now ISO] [--persist]
python -m saathi.credentials.cli m44-validate-rollout --request-file REQ.json [--now ISO]
python -m saathi.credentials.cli m44-list-rollouts     # rollout IDs in the ledger
python -m saathi.credentials.cli m44-show-rollout ROLLOUT_ID
python -m saathi.credentials.cli m44-expire-rollout ROLLOUT_ID [--reason ...]
python -m saathi.credentials.cli m44-verify-ledger     # hash-chain integrity
python -m saathi.credentials.cli m44-emit-evidence     # writes docs/evidence/m44/*.json
```

There are **no** production-execution commands, by design.

Exit codes: `0` success/advisory-validated, `5` not-ready / validation-failed /
chain-broken, `2` invariant violation or leak detected.

## Evidence resolution (M44.1)

`m44-status` reports `current_graduation_state` derived from:

1. the **live** M42 review (machine-override-aware — prefers
   `docs/evidence/m43/machine_verified_canary_completion.json` over the
   operator-attested M41 artifact);
2. M44's own `verify_machine_record` (requires `source=MACHINE`,
   `machine_verified` + `machine_verified_live`, CLOSED lifecycle + HTTP 401,
   provider `github_meta`, clean identity/scope signals).

The stored file `docs/evidence/m42/graduation_recommendation.json` is **never
trusted as a string** (it is stale pre-proof `GRADUATION_NOT_RECOMMENDED`). A
recommendation is **advisory only** — it is not authorization.

CLI `m44-validate-rollout` / `m44-review-rollout` use a deny-by-default
`RuntimeSnapshot`. Even with a perfect evidence chain, runtime gates block unless
a separate, future runtime-attestation path supplies proof. That is intentional:
M44 cannot imply live rollout readiness from the CLI alone.

## Building a rollout request

A request is a JSON object with every mandatory field. Fingerprints are references,
never secrets.

```json
{
  "rollout_id": "R-2026-0001",
  "operator_identity": "operator:ajay",
  "approval_timestamp": "2026-07-22T00:00:00+00:00",
  "expiration": "2026-08-22T00:00:00+00:00",
  "purpose": "bounded read-only canary of github_meta /meta",
  "scope": "read_only:github_meta:/meta",
  "provider": "github_meta",
  "resource": "github_meta:/meta",
  "rollout_percent": 1,
  "risk_level": "low",
  "rollback_owner": "operator:rollback-owner",
  "incident_owner": "operator:incident-owner",
  "policy": "ReadOnlyLimited",
  "approval_fingerprints": ["<m39.3 approval record fingerprint>"],
  "evidence_fingerprints": ["<m43 machine record fp>", "<m42 graduation fp>"],
  "acknowledgements": [
    "I_CONFIRM_FRAMEWORK_READINESS_IS_NOT_AUTHORIZATION",
    "I_CONFIRM_NO_PRODUCTION_ACTIVATION",
    "I_CONFIRM_NO_WRITE_AUTHORITY",
    "I_CONFIRM_ROLLBACK_OWNER_ASSIGNED",
    "I_CONFIRM_INCIDENT_OWNER_ASSIGNED",
    "I_CONFIRM_BOUNDED_REVERSIBLE_ROLLOUT",
    "I_CONFIRM_SEPARATE_EXECUTION_AUTHORIZATION_REQUIRED",
    "I_CONFIRM_TRADING_GUARDIAN_REMAINS_UNENGAGED"
  ],
  "operator_signature": "<HMAC over the canonical core>"
}
```

Sign it in-process:

```python
from saathi.credentials import m44
req = m44.RolloutRequest(**fields)         # fields without the signature
req.operator_signature = m44.sign_request(req)
```

Any later edit to a signed field invalidates the signature and the request is
denied.

## Policies

| Policy | Max % | Allowed % | Notes |
|--------|-------|-----------|-------|
| `ReadOnlyLimited` | 5 | 1, 2, 5 | default bounded read-only canary |
| `ReadOnlyExtended` | 25 | 1, 2, 5, 10, 25 | wider read-only band |
| `ProductionCandidate` | 10 | 1, 2, 5, 10 | low/medium risk only |
| `IncidentRecovery` | 5 | 1, 2, 5 | high/critical risk only |
| `EmergencyRollback` | 0 | 0 | rollback framing; no graduation required |
| `DryRun` | 0 | 0 | no evidence chain required |
| `Simulation` | 0 | 0 | offline wiring proof |

Percentages outside `{0,1,2,5,10,25,50,100}`, above the policy ceiling, negative,
fractional, or missing are rejected by the percentage guard.

## Interpreting a verdict

- `ROLLOUT_REQUEST_INCOMPLETE` — fill the listed `missing:*` fields.
- `ROLLOUT_VALIDATION_FAILED` — read `blockers`; each names the failed check
  (`gate:*` are runtime-gate blockers).
- `ROLLOUT_AUTHORIZATION_VALIDATED_ADVISORY_ONLY` — the request is sound. **This is
  not permission to execute.** Route it to the separate execution-authorization
  process.

## Why a valid request may still fail via the CLI

The CLI cannot attest a live `RuntimeSnapshot`, so `m44-review-rollout` applies the
default (deny-by-default) snapshot and will block on `gate:machine_proof_absent` /
`gate:operator_approval_absent`. This is intentional and safe. Use `m44-simulate`
to see the wiring end-to-end with an injected safe snapshot.
