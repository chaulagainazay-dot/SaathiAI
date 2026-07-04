# Stage 2 — Logto Authentication (JWT · RBAC · Organizations)

Puts a real identity provider in front of the CEO Gateway. **Additive and env-gated:**
until `LOGTO_ENDPOINT` is set, the platform behaves exactly as before (token/session auth).
Once configured, a valid Logto access token is an accepted identity, with RBAC via scopes.

```
UI → CEO Gateway → Auth (Logto JWT/JWKS) → Governance → Executive Intelligence → …
```

## 1. Run Logto
```bash
docker compose -f docker-compose.logto.yml up -d
# admin console: http://localhost:3002   (create your account on first visit)
# OIDC endpoint: http://localhost:3001
```

## 2. Configure in the Logto admin console
1. **API resource** → create one, e.g. indicator `https://api.saathi.local`. This becomes the
   token **audience**.
2. **Permissions (scopes)** on that resource, e.g. `ceo:read`, `ceo:approve`, `ceo:admin`.
3. **Roles** (RBAC) → e.g. `CEO` with all three scopes; `Viewer` with `ceo:read`.
4. **Application** → create a *Traditional Web* (or SPA) app for the Next.js UI; note its App ID/secret.
5. **Organizations** (optional) → e.g. `Hospital`, `Travel Office`; assign members + org roles.
   Org tokens carry `organization_id` (audience `urn:logto:organization:<id>`).

## 3. Point the platform at Logto
Add to `~/SaathiAI/.env` (never commit):
```
LOGTO_ENDPOINT=http://localhost:3001
LOGTO_API_RESOURCE=https://api.saathi.local
```
Restart the API (`.venv/bin/python -m saathi.server`). The gateway now:
- verifies `Authorization: Bearer <jwt>` against `…/oidc/jwks` (RS256),
- checks issuer `…/oidc` and audience `LOGTO_API_RESOURCE`,
- exposes the caller as `request.state.principal` (`subject`, `scopes`, `roles`, `organization_id`),
- still accepts the legacy `x-saathi-token` and the existing session (backward compatible).

RBAC is enforced with `principal.has_scopes([...])` / `authorize(header, required_scopes=[...])`
in `saathi/auth_logto.py` — add per-route scope requirements as you lock endpoints down.

## 4. Wire the Next.js UI (CEO Companion)
Install the SDK and add sign-in:
```bash
cd saathi-os && npm i @logto/next
```
Set `saathi-os/.env.local`:
```
LOGTO_ENDPOINT=http://localhost:3001
LOGTO_APP_ID=<app id from step 2.4>
LOGTO_APP_SECRET=<app secret>
LOGTO_COOKIE_SECRET=<openssl rand -base64 32>
LOGTO_BASE_URL=http://localhost:3000
NEXT_PUBLIC_SAATHI_API=http://localhost:8765
```
Then use `@logto/next/server-actions` (App Router) for `signIn` / `signOut` / `getLogtoContext`,
request an access token for the `https://api.saathi.local` resource, and send it as
`Authorization: Bearer <token>` from `lib/api.js`. (The BFF `/api/executive/briefing` and
`/api/events/stream` are currently whitelisted for the local companion; remove them from the
whitelist in `saathi/server.py` once the UI attaches tokens, to require sign-in.)

## Verified
`tests/test_auth_logto.py` (8 tests) proves offline JWT verification: valid → Principal with
scopes; expired / wrong-issuer / wrong-audience / tampered-signature all rejected; RBAC scope
enforcement; organization claim carried through. No network in tests (local RSA key injected).

## Roadmap note
This is Stage 2. It slots cleanly before Stage 3 (Redis/Postgres/workers) — Logto already uses
Postgres, so Stage 3's Postgres can host both. The API-gateway boundary Logto establishes is what
later lets Stage 6 (private AI mesh across hospital / travel / home / GPU) authenticate remote
workers with the same identity model.
