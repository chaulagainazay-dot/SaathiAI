# M41 — Bounded Read-Only Canary Rollout

**Status:** LAYER COMPLETE — CANARY_NOT_ACTIVATED (deny-by-default; operator approval
record + M40 live certification required to activate).
**Branch:** `milestone/m41-canary-rollout`.
**Module:** `saathi/credentials/m41.py` (composes M39.3 + M40 + M39.5).
**Tests:** `tests/test_m41_canary_rollout.py` — 17 passed.
**Evidence:** `docs/evidence/m41/` (deterministic; leak-clean).

## Scope (operator constraints)

Provider `github_meta` only · read-only · sandbox/canary · scope expansion FORBIDDEN ·
writes FORBIDDEN · production FORBIDDEN · active mode FORBIDDEN · Trading Guardian
unchanged/unengaged · operator approval MANDATORY · automatic rollback MANDATORY ·
kill switch MANDATORY.

## What M41 is — and is NOT

M41 is an operator-authorized **bounded read-only canary verification rollout** for the
single LIVE-certified provider. It is a distinct governed surface that composes M40's
read-only single-session runner under continuous rollback monitoring.

**M41 does NOT touch the M32 provider-runtime prohibition of `ExecutionMode.CANARY` /
`ExecutionMode.ACTIVE`** — that gate is unchanged (`m32_canary_execution_mode:
PROHIBITION_UNCHANGED`, verified by test). M41 canary is not the M32 execution mode; it
is bounded read-only verification traffic, operator-authorized, auto-rolled-back.

## Authorization (deny-by-default)

`validate_canary_authorization` requires ALL of:
- a **valid M39.3 operator canary approval record** (10 fields + 5 acks, scope within
  github_meta / user,meta / GET, rollout 1–5%);
- **M40 `LIVE_CERTIFIED`** evidence for `github_meta`, `read_only:true`;
- rollout percent within the 1–5% ceiling; bounded increments.

Absent any → `CANARY_NOT_ACTIVATED`. Never grants active/production/write.

## State machine + verdicts

`CANARY_NOT_ACTIVATED` (unauthorized) · `CANARY_BLOCKED` (kill switch pre-check) ·
`CANARY_ACTIVE_BOUNDED` (bounded rollout completed, read-only) · `CANARY_ROLLED_BACK`
(a trigger fired mid-rollout → auto-rollback).

## Mandatory safety (verified by tests)

- **Automatic rollback**: after every increment, any M39.5 alert (auth denial, secret
  failure, provider failure, lease leak, leak finding) or kill switch → immediate halt +
  rollback. Zero error budget by default. Rollback closes SecretHandles.
- **Kill switch**: `SAATHI_M39_KILL_SWITCH` blocks before start and halts mid-rollout.
- **Bounded**: rollout ≤ 5%, bounded increments, read-only github_meta /user + /meta.

## Operator activation (when ready)

Requires a fresh disposable credential (as in M40) + a signed approval record:

```bash
python -m saathi.credentials.cli m41-run-canary \
  --approval-file operator_canary_approval.json \
  --cert-file docs/evidence/m40/live_certification_record.json \
  --source-kind OS_KEYCHAIN_REFERENCE --locator <service>:<account> \
  --expected-subject-fp <fingerprint> --rollout-percent 1 --live-flag \
  --ack ...(10 M39 acks)
```

Rehearse first (no credential): `python -m saathi.credentials.cli m41-rehearsal`.

## Authority state (unchanged)

CANARY EXECUTION: bounded read-only only, never persisted as ACTIVE. ACTIVE / PRODUCTION
/ ROLLOUT(full) / WRITE: **NOT GRANTED**. Trading Guardian **UNENGAGED**.
