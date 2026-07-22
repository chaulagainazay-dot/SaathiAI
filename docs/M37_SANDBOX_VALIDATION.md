# M37 — Sandbox Validation

## Path

Full lifecycle through the provider contract + M36 primitives:

1. capabilities / qualification / health
2. M36 authorization (8 acknowledgements)
3. account registry + lease
4. secret retrieve by reference → SecretHandle
5. fingerprint derivation
6. provider.identity (budget call 1)
7. provider.operation (budget call 2)
8. lease consume + revoke
9. handle close / zeroize
10. provider.cleanup

## Offline

Fixture transport (path-aware) simulates `/user` and `/meta`. No network.
Certification: `SECURITY_CERTIFIED_WITH_LIMITATIONS` (live not exercised).

## Live (operator)

Requires disposable Keychain reference + `SAATHI_M37_ALLOW_LIVE_SANDBOX_VERIFICATION=1`
+ M36/M37 acknowledgements. Not exercised in CI.

## Guarantees

- No plaintext secret in logs/stdout/evidence/exceptions
- Handle closed on success and failure
- Lease revoked after session
- Call budget ≤ 3
