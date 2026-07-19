# M39 — External Credential Revocation

## Policy

External revocation is a **manual operator action** for GitHub PATs.

SaathiOS does **not** implement token-deletion authority for M39.

## Status this run

**PENDING** — no live credential was used; no revocation required for offline path.

When live is exercised:

1. Complete local cleanup  
2. Close handles; revoke leases; mark sessions CLEANED  
3. Operator revokes token in GitHub UI  
4. Record via `m39-confirm-external-revocation --confirmed`  
5. Optional post-revoke auth check only if policy, budget, and operator authorize  

M39 cannot reach fully closed live success without revocation confirmation
(`BLOCKED_EXTERNAL_REVOCATION_REQUIRED` if live passed but unconfirmed).
