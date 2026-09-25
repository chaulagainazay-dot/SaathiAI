# SaathiOS — Single-Origin Topology

**Builds on frozen auth/session baseline `fa3d5441`.** Scope: make the browser talk to SaathiOS through ONE first-party origin (`http://localhost:3100`); the backend (`:8765`) becomes an internal loopback that the browser never contacts directly. **Authentication transport is unchanged** (still `localStorage` + `x-baadar-session` via `afetch`) — cookie migration is the *next* milestone.

## Previous → final topology
- **Before:** browser → UI `:3100` for pages, but API/SSE/voice directly to `http://127.0.0.1:8765` (cross-origin; CORS-dependent).
- **After:** browser → `:3100` only. `:3100/api/{v1,executive,events,content}/*` is proxied server-side to the fixed loopback backend `http://127.0.0.1:8765`. Production behind Caddy is unchanged (Caddy proxies `/api` at the edge before Next).

## Routing mechanism — Next.js rewrites (KEEP)
`next.config.mjs` `rewrites()` (afterFiles) forwards a **closed, explicit set** of backend prefixes to a **fixed** upstream (`SAATHI_API_BASE` || `http://127.0.0.1:8765`). Local `app/api/*` route handlers (nepse/analysis/browser/news/…) are disjoint and resolve first, untouched.
- Alternatives: **Caddy/reverse-proxy REJECT** (extra permanent service; prod already has Caddy at its edge); **custom proxy service REJECT** (unneeded on 8 GB); **catch-all `/api/:path*` REJECT** (would shadow local routes + widen surface); explicit prefixes **KEEP**.
- SSE proven through the rewrite: `content-type: text/event-stream`, `x-accel-buffering: no`, frames arrived at t=0 and t≈4s (streamed, **not buffered**).

## Browser API contract
`NEXT_PUBLIC_SAATHI_API=""` (same-origin) → `afetch` builds relative `/api/...`. `start_local.sh` exports `""` (empty = same-origin; `SAATHI_OS_DATA` remains the absolute multi-host override). Four pages that used `NEXT_PUBLIC_SAATHI_API || "http://localhost:8765"` were fixed to `??` so `""` is honored (not treated as falsy). Methods/bodies/content-types/status/headers/401 semantics unchanged — forwarded verbatim by the rewrite.

## Evidence (live)
Browser network on `:3100`: every backend call is `http://localhost:3100/api/...`, **zero `:8765`** requests. Same-origin: protected GET no-auth → **401**, authed (`x-saathi-token`) → **200**; chat list no-auth 401 / authed **200**; POST body+content-type forwarded (backend JSON error propagated); SSE `/api/events/stream` streamed; `/api/v1/voice/enroll` no-auth **401** (still gated), `/api/v1/voice/providers` gated. Backend still directly reachable at `127.0.0.1:8765` (200) for CLI/services. `:3000` no listener.

## Auth / authority unchanged
`git diff fa3d5441 -- saathi/` is **empty** — no backend code changed. Exact-once auth-loss recovery (dedup 12/12), mutation no-replay (12/12), session cap/marker (focused 20/20), voice policy, ExecutionGateway/Trading Guardian/RBAC/approvals/audit/broker/paper-live all byte-identical. No cookie/CSRF/SameSite/KDF work (deferred).

## Proxy security
Upstream is a **fixed** loopback const, never derived from the request — no open proxy, no browser-supplied upstream (enforced by `lib/single-origin.test.js`). Closed prefix list (no catch-all). Host is fixed to loopback → path tricks can't redirect off-host. No credential logging added; `x-baadar-session`/`Authorization` forwarded but never logged.

## CORS
Backend CORS unchanged (`:3100` still allowed). Browser operation **no longer depends** on frontend→backend CORS (same-origin now). Narrowing/removal deferred to a later hardening phase (CLI/tools/tests may still use explicit origins).

## Ports
`:3100` = frontend + first-party browser API · `:8765` = internal loopback backend (CLI/services) · `:3000` = retired (no listener). Restart path: `launchctl kickstart -k gui/$(id -u)/com.saathi.local`.

**Verdict: SAATHIOS_SINGLE_ORIGIN_TOPOLOGY_CERTIFIED.** Next: `M — FIRST_PARTY_HTTPONLY_COOKIE_AUTH` (not started).
