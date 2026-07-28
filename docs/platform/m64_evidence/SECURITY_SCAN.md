# M64 — Security and Evidence Scan

Scope: M64 backend registry/API/config, frontend discovery/provider/shell/navigation/
route-boundary/palette/dashboard, tests, browser certificate, documentation, JSON,
and screenshots.

## Executable-loading review

| Pattern | Classification |
|---|---|
| `eval`, `exec`, `new Function`, `Function(` | no executable use; matches are words such as `evaluate*`, `ExecutionGateway`, and Playwright `waitForFunction` |
| `dangerouslySetInnerHTML`, raw `innerHTML`, `document.write` | none |
| `import(...)` | one fixed local lazy import of `../platform-client.js`; no metadata-derived path |
| subprocess, socket, requests/httpx/urllib/websocket in M64 path | none introduced |
| filesystem/plugin/module path from metadata | none |
| arbitrary component/icon lookup | none; fixed glyph allowlist with neutral fallback |

## Authority review

- Module endpoints authenticate a real platform context and require `PLATFORM_READ`.
- Backend `ModuleRegistry.discovery()` supplies status, state, capability, route,
  navigation, dashboard, and health truth.
- Frontend fallback can delay/deny presentation but cannot grant access.
- Production Sidebar, CommandPalette, Applications dashboard, and route boundary
  consume the shared authenticated backend response.
- Route guards are presentation only; backend RBAC and service permissions remain
  authoritative.
- Registration declares namespaces but grants no permission.
- Permission-restricted modules expose no actionable route.
- Placeholders expose no actionable card, command, or route content.
- Context/token generation checks, aborts, and timer cleanup prevent stale responses
  after logout or tenant/workspace switch.
- No cache exists, so there is no cross-tenant module-cache reuse.

## Secret/evidence review

Scans covered Authorization/Bearer/password/secret/API-key/credential/access-token/
refresh-token/session-token/cookie/private-key/database/private-home-path/JWT/cloud-
key patterns. Results:

- no raw credential, bearer value, cookie, private key, JWT-like value, or cloud key;
- no database content or `storage.db`;
- no private absolute filesystem path in JSON/evidence;
- browser authentication material remained in memory and was never logged or written;
- discovery and browser JSON key/value scans passed;
- four screenshots were visually inspected and contain only local module UI;
- no developer tools, query authentication data, personal messages, or unsafe stack
  trace is captured.

Literal `/Users/` matches exist only as forbidden-string test needles. `token`,
`secret`, and `credential` matches are identifiers or security documentation, not
values.

## Listener and trading review

- default host is `127.0.0.1`; explicit deploy override remains supported;
- certified listeners are one Python process on `127.0.0.1:8765` and one Next process
  on `127.0.0.1:3000`; no `0.0.0.0` listener;
- no untrusted plugin loading, deployment, production database change, broker,
  live-trading capability, or Trading authority change.

## Verdict

**PASS.** No M64 authority, secret, executable-loading, cross-tenant, placeholder,
listener, or Trading safety gate failed.
