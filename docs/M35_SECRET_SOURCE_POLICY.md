# M35 — Secret Source Policy

`validate_secret_source` (`saathi/credentials/m35.py`) classifies every secret
source, fail-closed. Built on the M31 `SecretBackend` contract.

## Source kinds

| Kind | M35 behaviour |
|------|---------------|
| `IN_MEMORY_TEST` | fully exercised — the **only** retrievable source |
| `ENV_REFERENCE` | structural validation only — never retrieved |
| `OS_KEYCHAIN_REFERENCE` | structural validation only — no keychain access |
| `ENCRYPTED_STORE_REFERENCE` | structural validation only |
| `EXTERNAL_SECRET_MANAGER_REFERENCE` | structural validation only |

Requesting retrieval (`want_retrieval=True`) from any non-retrievable source fails
closed (`secret_source_not_retrievable`).

## Prohibited sources (always fail closed)

`PLAINTEXT`, `REPOSITORY_FILE`, `COMMAND_LINE_VALUE`, `LOG_EMBEDDED`,
`EVIDENCE_EMBEDDED`, `CALLER_RAW_SECRET` → `prohibited_secret_source`.
Unknown sources → `unknown_secret_source`.

## Rules

- Callers provide a **reference**, never raw secret material.
- Retrieval is explicit, requires an approval + active lease + matching session,
  and is bounded to that session.
- Retrieved bytes are never persisted; they live only inside a `SecretHandle` and
  are zeroized on close.
- **No fallback** between sources (`fallback_permitted: false`); no automatic
  search for credentials.
- The CLI never accepts a raw secret as a positional or flag value.
