# M46 — Implementation

## Purpose

Composition-only controller for **one** execution class:

```
READ_ONLY_DISPOSABLE_CANARY
```

Module: `saathi/credentials/m46.py`
CLI: `m46-*` in `saathi/credentials/cli.py`
Tests: `tests/test_m46_bounded_canary.py`

## Architecture

```
Approval (signed) → M44 request + M45 snapshot → ExecutionPlan
        → preflight → reserve consume (ATTEMPTED)
        → M39 one-call GET /user → finalize consume (SUCCESS|FAILED)
        → operator external revoke → m46-run-revocation (1 call)
        → HTTP 401 only → optional Keychain delete
```

### Components

| Piece | Role |
|-------|------|
| `validate_approval` / `sign_approval` | Operator approval integrity |
| `create_plan` / `verify_plan_integrity` | Tamper-evident plan |
| `preflight` | Fail-closed composition |
| `run_canary` | Live/simulate controller |
| Consumed ledger | Durable one-shot (`consumed_authorization.local.jsonl`) |
| `validate_live_canary_evidence` | Revocation evidence contract |
| `run_revocation` / CLI cleanup | 401-gated Keychain delete |

## Endpoint Model A

`IDENTITY_READ` requires `allowed_endpoint == "user"`.
Live path uses **exactly** `GET /user` (one network call).
`meta` is **not** an alias for `/user`.

Historical canary with signed `meta` + live `/user` is classified
`M46_ENDPOINT_BINDING_EXCEPTION` and must not certify the policy path.

## Evidence schemas

| Schema | Revocation acceptance |
|--------|----------------------|
| `m46.canary_result.v1` | `live_canary_occurred is True` (boolean) |
| `m46.live_canary_evidence.local.v1` | same |
| `m46.fresh_policy_canary.local.v1` | success `resulting_state` + calls=1 + endpoint user + IDENTITY_READ + subject_match |
| `m46.fresh_policy_canary.local.v2` | includes **explicit** `live_canary_occurred: true` (preferred) |

**Absent `live_canary_occurred` is never treated as true** on controller/local schemas.

Use `build_policy_canary_evidence()` for new local records.

## Replay / consume

Path: `docs/evidence/m46/consumed_authorization.local.jsonl` (gitignored).

1. `reserve_authorization_attempt` under exclusive lock → `ATTEMPTED`
2. Provider call (max 1)
3. `finalize_authorization_consume` → `CONSUMED_SUCCESS` or `ATTEMPTED_FAILED`

Crash after `ATTEMPTED` fails closed (no second live). Corrupted ledger fails closed.

## Cleanup

CLI `--cleanup-after-401`:

- Runs only if `http_401_confirmed`
- Deletes only service/account from locator
- No second GitHub call
- HTTP 200/403/timeout ⇒ no delete

## Non-grants

Closed or open M46 **never** grants production, deployment, write, trading,
autonomous execution, or rollout expansion. Trading Guardian stays unengaged; M32 unchanged.

## Related docs

- `docs/M46_OPERATOR_GUIDE.md`
- `docs/M46_APPROVAL_SCHEMA.md`
- `docs/evidence/m46/historical_endpoint_binding_exception.json`
