# M45 — Runtime Attestation and Bounded Rollout Readiness (Implementation)

## Purpose

M45 is a composition-only layer above M39–M44 that produces, validates, binds,
expires, and audits a **machine-attested RuntimeSnapshot**.

It does **not** execute a provider rollout. Maximal advisory state:

```
M45_RUNTIME_ATTESTATION_READY_ADVISORY_ONLY
```

A fully valid M44 request + M45 snapshot evaluation may reach:

```
BOUNDED_ROLLOUT_READY_FOR_SEPARATE_OPERATOR_AUTHORIZATION
```

— which still **grants nothing**. Execution requires a separate operator
authorization outside M44/M45.

## Why M45 exists (M44 runtime gap)

M44's `RuntimeSnapshot` is a **caller-supplied flag bag**. Defaults deny
(`machine_proof_present=False`, `operator_approval_present=False`). Callers can
set flags true without machine observation. M45 supplies a deterministic,
integrity-protected, evidence-bound snapshot so readiness cannot be self-asserted.

## Components

| Component | Location |
|-----------|----------|
| Module | `saathi/credentials/m45.py` |
| Tests | `tests/test_m45_runtime_attestation.py` |
| CLI | `saathi/credentials/cli.py` (`m45-*`) |
| Evidence | `docs/evidence/m45/*.json` |
| Docs | `docs/M45_*.md` |

## Subsystems

1. **RuntimeSnapshot contract** — `RuntimeAttestationSnapshot` with required fields.
2. **Collector** — local, secret-free observation; UNKNOWN ⇒ ineligible.
3. **Machine attestation** — canonical serialization + HMAC fingerprint/signature
   (tamper evidence only; not operator identity; not hardware).
4. **Eligibility validator** — expiry, provenance, identity, provider, scope,
   safety switches, evidence bindings, percent ceiling.
5. **Lifecycle ledger** — append-only hash-chained events.
6. **M44 integration** — `to_m44_runtime_snapshot` + `check_request_readiness`.
7. **CLI** — status, create/validate/verify/show/list/expire/invalidate, readiness,
   simulate, emit-evidence. **No execution commands.**

## Composition

- M39 — provider, authorities, kill switch, HMAC domain
- M42/M43/M43.1 — evidence fingerprints (read-only)
- M44 — policies, request validator, gate interface

## Forbidden

No production activation, deployment, push, write enablement, scope expansion,
raw credentials, provider calls, M32 change, Trading Guardian engagement, or
historical evidence rewrite.
