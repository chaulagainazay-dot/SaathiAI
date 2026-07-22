# M37 — Provider Model

## Contract

`saathi/credentials/sandbox_provider.py` defines `SandboxProvider`:

| Method | Purpose |
|--------|---------|
| `capabilities()` | Read-only capability ceiling (no secrets) |
| `qualification(**kwargs)` | Disposable sandbox identity qualification |
| `health(transport=)` | Structural provider health (offline-safe) |
| `identity(transport, handle, session_id, …)` | Authenticated identity via M36 sender wrapper |
| `operation(transport, handle?, session_id, …)` | Approved read-only operation |
| `cleanup(session_id, reason)` | Provider-side cleanup attestation |

Callers resolve providers via `resolve_sandbox_provider(provider_id)` — no
provider-specific branching upward.

## Reference implementation

`GithubMetaSandboxProvider` (`provider_id=github_meta`):

- Identity: `GET /user` (auth required; Authorization only in sender context)
- Operation: `GET /meta` (auth not required)
- Host: `api.github.com` (M33 allowlist)
- Transport: M33 `ExternalTransport`
- Auth: M36 `make_authenticated_sender` + `SecretHandle`

## Registry

Only governed providers may register. Expanding the registry requires explicit
milestone authorization. M37 ships **one** provider: `github_meta`.

## Non-goals

No parallel transport, no credential store, no write operations, no financial/
trading providers, no rollout activation.
