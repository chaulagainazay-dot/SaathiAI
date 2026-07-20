# M42 — Evidence Chain Audit

Machine-read audit of the M40/M41 evidence chain. All artifacts leak-clean; no raw
secret, authorization header, or PAT fragment present.

## Artifacts reviewed & provenance

| Artifact | Path | Status | Provenance |
|----------|------|--------|-----------|
| M40 live-certification record | `docs/evidence/m40/live_certification_record.json` | PRESENT_VALID | **MACHINE_PROOF** |
| M40 validation phase | `docs/evidence/m40/live_certification_validation_phase.json` | PRESENT_VALID | MACHINE_PROOF |
| M40 revocation phase | `docs/evidence/m40/live_certification_revocation_phase.json` | PRESENT_VALID | MACHINE_PROOF |
| M41 bounded-canary completion | `docs/evidence/m41/operator_attested_canary_completion.json` | **INCONSISTENT** | **OPERATOR_ATTESTED** |
| M41 rehearsal (bounded) | `docs/evidence/m41/canary_rehearsal_bounded.json` | PRESENT_VALID | SIMULATED_NOT_LIVE |
| M41 rollback proof (rehearsal) | `docs/evidence/m41/canary_rehearsal_auto_rollback.json` | PRESENT_VALID | SIMULATED_NOT_LIVE |
| M41 summary | `docs/evidence/m41/summary.json` | PRESENT_VALID | SIMULATED |

`INCONSISTENT` on the M41 bounded-canary artifact = machine proof expected, operator
attestation observed. This is the decisive finding.

## Provenance classification (machine vs attestation)

- **Machine-generated proof**: the entire M40 chain. M40 executed the real GitHub
  provider in-session — `live_exercised: true`, `decision: LIVE_CERTIFIED`, revocation
  `http_401_confirmed: true`. Independently reproducible.
- **Operator attestation**: the M41 bounded-canary *live* completion. The canary ran
  in the operator's environment; this repo holds only the operator's attestation
  (`source: OPERATOR_ATTESTED`, `machine_verified_live: false`) plus machine
  **rehearsal** (simulated) evidence. The reported signals were re-evaluated through
  the M39.5 detector (0 alerts) and M41 rollback evaluator (no rollback) for
  consistency — consistent, but consistency of an attestation is not machine proof.

## Consistency result

`consistent: true` — provider `github_meta`, read-only, identity fingerprint present,
no prohibited grant anywhere, Trading Guardian unengaged in both cert and canary,
M40 live+revocation proven, M32 prohibition declared unchanged. No identity/provider/
scope drift, no contradictory verdicts.

## Conclusion

The chain is complete, internally consistent, and leak-clean, **but** the M41
bounded-canary completion is attestation-only where machine proof is required. Verdict:
`GRADUATION_NOT_RECOMMENDED`.
