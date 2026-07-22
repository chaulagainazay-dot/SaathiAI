# M46 — Revocation and Cleanup

Reuses the M43.1 lifecycle discipline:

1. Live bounded read completes → **stop**.
2. Operator revokes disposable credential **externally**.
3. `m46-run-revocation --mode live` observes **HTTP 401** (only conclusive proof).
4. HTTP 200 after claimed revoke → **fail closed**.
5. Operator removes local reference (Keychain/env).
6. `m46-verify-cleanup` proves **exact absence** (match_count=0).
7. `CLOSED_ADVISORY_ONLY` — still grants nothing.

Simulation never produces live revocation proof.
