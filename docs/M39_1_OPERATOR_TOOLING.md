# M39.1 — Operator Live-Validation Dry-Run Tooling

**Status:** OFFLINE OPERATOR TOOLING COMPLETE (offline readiness extension of M39).
**Series:** PRE-M40 offline readiness (`docs/PRE_M40_OFFLINE_READINESS_PLAN.md`).
**Module:** `saathi/credentials/m39_1.py` (composes M39; no new subsystem).
**Tests:** `tests/test_m39_1_operator_tooling.py` — 25 passed.
**Evidence:** `docs/evidence/m39_1/` (deterministic; leak-clean).

## Purpose

Reduce operator error at the live-validation boundary by giving the operator
offline, secret-free tooling to plan, preview, and prepare a live run *before* any
credential is supplied. Nothing here resolves or emits a secret value.

## Surface

| CLI command | Function | Output |
|-------------|----------|--------|
| `m39-1-plan` | `build_execution_plan` | Deterministic dry-run plan: provider, endpoints, methods, budgets, required acks, env flags, secret-reference fingerprint. Live outcomes remain `NOT_EXERCISED`. |
| `m39-1-preview` | `render_command_preview` | Human-readable, copy-pasteable command sequence. Secret shown only as `<REFERENCE>` / fingerprint. |
| `m39-1-backend-availability` | `check_backend_availability` | Structural availability of a secret-reference backend. Never calls `get()`. Fails closed to `UNKNOWN`. |
| `m39-1-revocation-checklist` | `generate_revocation_checklist` | Deterministic 5-step operator revocation checklist (REV-1…REV-5). |
| `m39-1-diagnostics` | `collect_offline_diagnostics` | Redacted environment/flag snapshot. |
| `m39-1-emit-evidence` | `emit_m39_1_evidence` | Writes deterministic, leak-scanned evidence to `docs/evidence/m39_1/`. |

## Backend-availability verdicts

- `AVAILABLE` — reference present in backend (value never read).
- `UNAVAILABLE` — reference confirmed absent, or backend unapproved.
- `UNKNOWN` — existence undeterminable → **fail closed** (never `AVAILABLE`).
- `BLOCKED_OPERATOR_ACTION_REQUIRED` — e.g. `ENCRYPTED_STORE_REFERENCE` needs operator wiring.
- `SIMULATED_NOT_LIVE` — `IN_MEMORY_TEST` fixture only.

## Security invariants (verified by tests)

- No function resolves a secret value; `check_backend_availability` uses `exists()`/`readiness()` only.
- Every entry point rejects a raw/token-shaped locator (`raw_secret_locator_rejected`).
- CLI commands inherit the M39 `reject_m39_forbidden_argv` guard (token-shaped args → exit 2).
- All outputs carry `contains_secret_values: false` and are leak-scanned before write.
- Deterministic outputs (stable fingerprints; no wall clock in evidence bodies).

## Authority state (unchanged)

- live single-session / multi-session / external revocation: **NOT_EXERCISED**
- CANARY: **NOT GRANTED** · ACTIVE: **NOT GRANTED** · M40 production authorization: **NOT GRANTED**
- Trading Guardian: **UNENGAGED**

## Reproduce

```bash
python -m pytest tests/test_m39_1_operator_tooling.py -q
python -m saathi.credentials.cli m39-1-emit-evidence   # deterministic
python -m saathi.credentials.cli m39-1-preview --mode single
```
