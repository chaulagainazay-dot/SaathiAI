# M44 — Architecture

## Position in the milestone chain

```
M39   live disposable sandbox validation        (authorities, provider identity, kill switch)
M39.3 operator canary approval records          (referenced by fingerprint)
M40   live certification                         (referenced via M43)
M41   bounded read-only canary rollout policy
M42   graduation review                          (referenced by fingerprint)
M43   machine-verified bounded canary proof      (referenced by fingerprint)
M44   ROLLOUT AUTHORIZATION FRAMEWORK  ← advisory-only; grants nothing
```

M44 sits above the proof-producing milestones and below any (future, separate)
execution milestone. It is a **decision-support and gating layer**, not an
execution layer.

## Data flow

```
                 RolloutRequest (all mandatory fields + operator signature)
                            │
                            ▼
        ┌───────────────────────────────────────────┐
        │            validate_request                │
        │                                            │
        │  completeness  ─► deny if any field missing│
        │  policy lookup ─► deny if unknown / live   │
        │  provider/identity/scope/risk              │
        │  percentage guard (discrete ceilings)      │
        │  expiration (not expired; ordered)         │
        │  acknowledgements (superset of required)   │
        │  operator signature (recompute + compare)  │
        │  evidence chain  ◄── load_evidence_index() │
        │      (machine proof / closed cred / grad)  │
        │  runtime safety gates  ◄── RuntimeSnapshot │
        └───────────────────────────────────────────┘
                            │
                            ▼
        verdict ∈ { INCOMPLETE, FAILED, VALIDATED_ADVISORY_ONLY }
                            │
                            ▼
             append_ledger (hash-chained, immutable)
                            │
                            ▼
                     Audit API (read-only)
```

## Component boundaries

| Component | Input | Output | Side effects |
|-----------|-------|--------|--------------|
| `RolloutRequest` | operator-supplied fields | canonical `core()` / `to_public()` | none |
| `sign_request` | request + identity | HMAC signature | none |
| `RolloutPolicy` / `POLICIES` | — | bounded envelope | none |
| `check_percentage` | policy, percent | blocker list | none |
| `runtime_gate_blockers` | snapshot, env | blocker list | reads env kill switch |
| `load_evidence_index` | base dir | `{fp: EvidenceDescriptor}` | reads evidence JSON (read-only) |
| `validate_request` | request + context | advisory verdict dict | none |
| `append_ledger` | event, payload | chained entry | appends JSONL |
| `audit_show_*` | rollout_id, ledger | read-only view | reads JSONL |

## Evidence chain by fingerprint (M44.1 reconciliation)

M44 never inlines evidence content. It resolves evidence by fingerprint against
**public provenance markers only**, and — critically — never trusts a stored
state-name string.

### The precedence rule

`m42.load_evidence` already defines the authoritative precedence: for the canary
completion artifact it **prefers the M43 machine record**
(`docs/evidence/m43/machine_verified_canary_completion.json`) over the
operator-attested artifact whenever the machine record exists on disk (the
`machine_override` in `m42.REQUIRED_ARTIFACTS`). `m42.run_graduation_review()` then
recomputes graduation from that override and clears the `AB-PROV` abort condition
when the canary is genuinely machine-proven.

M44 therefore derives graduation from the **live `m42.run_graduation_review()`**,
not from any stored `graduation_recommendation.json` file. `resolve_graduation_state`:

1. reads the M43 machine record and runs `verify_machine_record` on it —
   independently requiring `source == MACHINE`, `machine_verified` and
   `machine_verified_live` true, `credential_lifecycle.status == CLOSED`, and the
   Phase 6 `http_401_confirmed` destruction proof;
2. runs the live M42 review;
3. marks graduation recommended **only when both** the live review recommends **and**
   the machine record independently verifies (defence in depth).

`load_evidence_index` keys the M43 descriptor by the machine record's fingerprint
and the graduation descriptor by the **live review's** fingerprint.

### Why this reconciliation was needed

The stored `docs/evidence/m42/graduation_recommendation.json` was emitted **before**
the M43 machine proof existed (it reads `GRADUATION_NOT_RECOMMENDED`, fingerprint
`46b1ebf…`). The earlier M44 read that stale file and trusted its string, so it
reported the chain as un-graduated. The live review — machine-override-aware —
returns `GRADUATION_RECOMMENDED` (fingerprint `dbc63fd…`). M44.1 fixes M44 to consume
the live, verified state; the stale file's fingerprint is never indexed.

### State resolution table (current genuine repository state)

| Artifact | Fingerprint | Provenance (M44 verdict) | Loaded state | Precedence | Consumer | Effect |
|----------|-------------|--------------------------|--------------|-----------|----------|--------|
| `m42/graduation_recommendation.json` (stale, pre-proof) | `46b1ebf…` | stale / not trusted | `GRADUATION_NOT_RECOMMENDED` | **ignored** | — | none (not indexed) |
| `m43/machine_verified_canary_completion.json` | `8ecd04d3…` | `MACHINE_PROOF` (verified) | live+CLOSED+401 | machine override | live M42 review + M44 | clears AB-PROV; machine-proof criterion |
| live `m42.run_graduation_review()` | `dbc63fd7…` | `MACHINE_PROOF` | `GRADUATION_RECOMMENDED` | **authoritative** | M44 graduation criterion | graduation criterion satisfied (advisory) |
| M43.1 Phase 7 revalidation record | (binds `8ecd04d3…`) | machine-proof binding | `GRADUATION_RECOMMENDED_PENDING_CLEANUP` | audit binding | operator/audit | evidence binding record |

If real on-disk evidence does not meet a policy's requirements — no machine proof,
simulated/attested provenance, lifecycle not closed, missing 401, or graduation not
recommended — validation **fails closed**. The framework never manufactures
provenance, and a recommendation is advisory only, never authorization.

## Immutability model

The ledger is append-only JSONL. Each entry stores `prev_fingerprint` and its own
`fingerprint = HMAC(domain, {event, prev, payload})`. `verify_ledger_chain`
recomputes the chain and reports the first index where either the back-link or the
recomputed fingerprint disagrees — so any edit to a historical entry is detectable.

## Invariants enforced structurally

- `RolloutPolicy.permits_live_execution` is `False` for all built-ins; both
  `register_policy` and `validate_request` reject any policy where it is `True`.
- Every validation/status/simulation/evidence output hard-codes
  `authorizes_execution: false`, `grants_anything: false`, and the frozen
  `FRAMEWORK_AUTHORITY_STATE`.
- All writes are guarded by `leakscan.is_clean`.
- No code path in M44 calls a provider write, changes provider permissions, engages
  the Trading Guardian, or touches the M32 runtime prohibition.
