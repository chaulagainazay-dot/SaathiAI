# M32 — Rate-Limit Awareness

Module: `saathi/connectors/providers/ratelimit.py`

## Representation (`RateLimit`)

`limit`, `remaining`, `reset_at`, `retry_after`, `source` (`header|policy|none`),
`confidence` (`high|low|unknown`).

## Parsing (`parse_rate_limit`)

- Parses provider headers **only** through adapter policy. Non-dict inputs (e.g. a
  response body a caller might try to pass as headers) yield `source=none` — callers
  cannot spoof rate-limit metadata.
- Unreasonable values are clamped (`MAX_LIMIT`, `MAX_RETRY_AFTER=3600`,
  `MAX_RESET_HORIZON=24h`); malformed values are ignored safely (→ `None`).
- Recognized headers: `x-ratelimit-limit/remaining/reset` (and variants),
  `retry-after`.

## Honoring Retry-After (`honored_retry_after`)

Returns a delay to honor only when `retry_after ≥ 0`, `≤ max_retry_after`, and
`≤ remaining_deadline`. Otherwise `None` — no sleeping past the deadline, no
background retry storm. The runtime feeds this into `decide_retry`.

## Evidence

`safe_rate_limit_evidence` emits numeric/enum fields only (`privacy_safe: true`);
no sensitive headers ever reach evidence. The deterministic simulator emits a
real HTTP-style `429` with `Retry-After` for verification.

## Health effect

A `429` transitions provider health to `RATE_LIMITED` (distinct from connector
health); recovery is explicit via a subsequent successful observation.
