# M44 — Limited Rollout Authorization Framework (Implementation)

## Purpose

M44 builds the complete infrastructure required to **authorize future limited
rollouts**. It activates nothing. Its maximal output is advisory:

```
ROLLOUT_AUTHORIZATION_FRAMEWORK_READY
```

— never `PRODUCTION_READY`. Even a fully valid rollout authorization request yields
only `ROLLOUT_AUTHORIZATION_VALIDATED_ADVISORY_ONLY`: a machine-checked statement
that *if* an operator later chooses to execute, the request is well-formed, bounded,
and evidence-backed. **Any future rollout still requires a completely separate
operator authorization outside M44.**

## What was added

| Component | Location |
|-----------|----------|
| Framework module | `saathi/credentials/m44.py` |
| Test suite (77 tests, incl. M44.1) | `tests/test_m44_rollout_authorization.py` |
| CLI commands | `saathi/credentials/cli.py` (`m44-*`) |
| Evidence bundle | `docs/evidence/m44/*.json` (incl. `framework_completion.json`) |
| Docs | `docs/M44_*.md` |

## Composition-only

M44 introduces **no** parallel credential system, secret store, provider
permission, or evidence chain. It composes existing systems by reference only:

- **M39** — `AUTHORITIES`, `PROVIDER_ID` (`github_meta`), `_hmac` fingerprint
  domain, `kill_switch_active`.
- **M39.3** — operator approval records (referenced by fingerprint, never inlined).
- **M43** — machine-verified canary proof (referenced by fingerprint).
- **M42** — graduation recommendation (referenced by fingerprint).

## The 11 subsystems

1. **Rollout Authorization Engine** — `RolloutRequest` carries every mandatory
   field (`rollout_id`, `operator_identity`, `approval_timestamp`, `expiration`,
   `purpose`, `scope`, `provider`, `resource`, `rollout_percent`, `risk_level`,
   `rollback_owner`, `incident_owner`, `policy`, `approval_fingerprints`,
   `evidence_fingerprints`). `missing_fields()` enforces completeness; no rollout
   exists without all mandatory fields.
2. **Rollout Policy Objects** — `RolloutPolicy` registry: `ReadOnlyLimited`,
   `ReadOnlyExtended`, `ProductionCandidate`, `EmergencyRollback`,
   `IncidentRecovery`, `DryRun`, `Simulation`. Extensible via `register_policy`,
   which rejects any policy that would permit live execution.
3. **Rollout Validator** — `validate_request` checks approval presence, expiration,
   provider/identity, scope, risk, evidence chain, machine proof, closed credential
   lifecycle, percentage, operator signature, and required acknowledgements.
   Fail-closed: any mismatch denies.
4. **Percentage Guard** — `check_percentage` bounds rollout to the discrete ceilings
   `{0,1,2,5,10,25,50,100}` and each policy's own allowed subset; rejects negative,
   above-policy, fractional/non-integer, and missing.
5. **Runtime Safety Gates** — `runtime_gate_blockers` blocks on identity drift,
   provider/credential mismatch, active rollback, kill switch (snapshot or env),
   unresolved incident, open security alert, active Trading Guardian, violated M32
   prohibition, absent machine proof, or absent operator approval.
6. **Rollback Contracts** — `RollbackTrigger` enum + `evaluate_rollback`;
   deterministic (any fired trigger ⇒ automatic rollback).
7. **Rollout Ledger** — append-only, hash-chained JSONL (`append_ledger`,
   `verify_ledger_chain`); each entry commits to the previous fingerprint, making
   tampering detectable.
8. **Audit API** — read-only `audit_show_*` functions (rollout, approvals, evidence
   chain, validation, rollback history, incident history); never expose secrets.
9. **CLI** — `m44-create-rollout`, `m44-validate-rollout`, `m44-review-rollout`,
   `m44-show-rollout`, `m44-expire-rollout`, `m44-list-rollouts`, `m44-simulate`
   (+ `m44-status`, `m44-list-policies`, `m44-verify-ledger`, `m44-emit-evidence`).
   No production-execution commands exist.
10. **Tests** — positive, negative, tampering, expired, wrong provider/identity/
    evidence/percentage, policy violations, rollback, schema, serialization, and
    security regression.
11. **Documentation** — this file and the five companion docs.

## Verdicts

| Verdict | Meaning |
|---------|---------|
| `ROLLOUT_REQUEST_INCOMPLETE` | A mandatory field is missing (deny-by-default). |
| `ROLLOUT_VALIDATION_FAILED` | Fields present but a check failed. |
| `ROLLOUT_AUTHORIZATION_VALIDATED_ADVISORY_ONLY` | Well-formed + bounded + evidence-backed. **Authorizes nothing.** |

`ROLLOUT_DENIED` is the enum's fail-closed floor. No verdict authorizes execution;
every result carries `authorizes_execution: false` and
`requires_separate_execution_authorization: true`.

## Determinism & safety markers

Every output is JSON-serializable, leak-scanned (`leakscan.is_clean`), and carries
`contains_secret_values: false`, `grants_anything: false`, the frozen
`FRAMEWORK_AUTHORITY_STATE`, `m32_prohibition: "UNCHANGED"`, and
`trading_guardian: "UNCHANGED / UNENGAGED"`. Fingerprints are HMAC-SHA256 over a
domain-separated canonical encoding, so identical inputs yield identical outputs.
