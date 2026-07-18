# M36 — Scope Verification

## Observed sources

GitHub `X-OAuth-Scopes` response header on authenticated identity call.

## Classifications

| Result | Meaning |
|--------|---------|
| `VERIFIED_READ_ONLY` | Observed scopes are read-only |
| `VERIFIED_WITH_EXTRA_READ_SCOPE` | Extra read scopes present |
| `MISMATCHED` | Declared/observed mismatch |
| `WRITE_SCOPE_PRESENT` | Write/admin/billing/workflow → fail |
| `UNKNOWN` | Unknown material scope → fail |
| `DECLARED_ONLY_UNOBSERVED` | No provider scope metadata |

## Rules

Write/admin/billing/payment/trading/unknown material scopes fail closed.
Missing scope metadata is **not** silently treated as verified — certification
must state limitation honestly.
