# M33 — Provider Selection (final)

**Decision:** Option **A** — official credential-free read-only API.

## Selected

| Field | Value |
|-------|-------|
| provider_id | `github_meta` |
| display name | GitHub Meta (public infrastructure metadata) |
| owner | GitHub, Inc. |
| documentation | https://docs.github.com/en/rest/meta/meta#get-github-meta-information |
| environment | `sandbox` (external read-only pilot; production disabled) |
| endpoint | `https://api.github.com/meta` |
| endpoint class | `https_external` |
| operation | `get_meta` (GET) |
| auth profile | `none` |
| side-effect class | `READ_ONLY` |
| data classification | `PUBLIC` |
| rate-limit profile | `github_unauth` (60/hr; `x-ratelimit-*` headers; `retry-after` on 429) |
| network required (live verify) | yes (optional, operator-triggered) |
| terms review | `REVIEWED_ACCEPTABLE` |
| max verification state | `EXTERNAL_READ_ONLY_VERIFIED_WITH_LIMITATIONS` |

## Guarantees at selection time

- No API key, no account, no OAuth, no credential of any kind.
- GET/HEAD-only method policy; **only** `get_meta` (GET) is declared. No write method is reachable.
- Not financial, trading, payment, social-publishing, personal email, or personal calendar.
- Non-mutating: zero writes, zero account interaction — the `production GitHub mutation` prohibition is preserved.
- Endpoint is fixed in the canonical profile; runtime callers cannot supply a URL.

## Rejected alternatives (one-line)

- `cloudflare trace`, `ipify` — echo the caller's egress IP (privacy-conservative reject).
- `worldtimeapi`, `restcountries`, `date.nager.at`, `httpbin` — community/third-party ownership, weaker terms, or uptime limitations.
- Any financial/trading/social/email/calendar provider — hard-blocked and regression-tested.

## Runner-up kept on record

`https://www.githubstatus.com/api/v2/status.json` (official GitHub Statuspage JSON) — viable future read-only candidate; not selected because `api.github.com/meta` has a richer, more stable documented schema and first-party rate-limit headers.

See `docs/M33_EXTERNAL_PROVIDER_AUDIT.md` for the full candidate matrix and reasoning.
