# M34 — Operator Authorization

**Milestone:** M34 — Bounded Live Read-Only External Verification
**Provider:** `github_meta` · **Operation:** `get_meta` · **Method:** `GET` (read-only)
**Command version:** `m34.live_external_verify.v1`

---

## 1. Authorization contract

The live path is **fail-closed**: it runs only when **all four** operator acknowledgements
are present *and* the environment opt-in flag is set. Any missing acknowledgement blocks the
call with an explicit `missing_ack_*` blocker, `live_call: false`, and no network activity.

| Acknowledgement | CLI flag | Meaning |
|-----------------|----------|---------|
| Read-only | `--ack-read-only` | operator confirms a read-only `GET`, no writes |
| Network | `--ack-network` | operator confirms a real outbound network call is permitted |
| Non-production | `--ack-non-production` | operator confirms this is verification, not production authority |
| Call budget | `--ack-call-budget` | operator confirms the bounded call budget (default 3, max 5) |
| Env opt-in | `SAATHI_M34_LIVE_VERIFY_ENABLED=1` | live path disabled by default; never set in CI/tests |

## 2. Approved authorization record

From `docs/evidence/m34/authorization.json` (`operator_authorized: true`):

| Field | Value |
|-------|-------|
| `provider_id` | `github_meta` |
| `operation` | `get_meta` |
| `approved_call_budget` | `3` |
| `approved_deadline` | `5.0` s |
| `approved_response_limit` | `262144` bytes (256 KiB) |
| `approved_redirect_limit` | `0` |
| `approved_data_classification` | `PUBLIC` |
| `read_only_acknowledged` | `true` |
| `network_acknowledged` | `true` |
| `non_production_acknowledged` | `true` |
| `call_budget_acknowledged` | `true` |

## 3. What this authorization does **not** grant

- No writes, no mutation, no non-GET method.
- No credential, no token, no OAuth, no account link.
- No second provider, no second endpoint, no additional operation.
- No rollout change — connector / provider / inference stay **OFF**; canary/active stay **0/0**.
- No change to the Trading Guardian — it remains **UNCHANGED / UNENGAGED**.

## 4. Live-call budget guarantee

The approved budget is **3 on-network calls, retries included**. Retries consume budget;
security and schema failures are terminal and never retried. The runtime enforces
`actual_call_count ≤ approved_call_budget ≤ 5` (`test_actual_calls_never_exceed_budget`,
`test_retry_consumes_budget`). Budgets `≤ 0` and `> 5` are rejected before any call.

## 5. Operator invocation (live)

```
SAATHI_M34_LIVE_VERIFY_ENABLED=1 \
  python -m saathi.connectors.providers external-verify github_meta \
  --ack-read-only --ack-network --ack-non-production --ack-call-budget
```

Non-mutating status reads (no acks, no network):

```
python -m saathi.connectors.providers reliability-status github_meta
python -m saathi.connectors.providers canary-readiness github_meta
python -m saathi.connectors.providers external-live-drift github_meta
```

## 6. Status in this session

The on-network live call was **NOT exercised**. All authorization evidence was produced
from the offline fixture-backed simulation. Live authorization remains available to the
operator; it has not been used.
