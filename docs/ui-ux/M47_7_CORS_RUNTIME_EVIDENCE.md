# M47.7 — CORS Runtime Evidence

**Date:** 2026-07-23  
**BFF under test:** managed `http://127.0.0.1:8766` (current `saathi.server:app` + `cors_policy.py`)  
**UI origin:** `http://127.0.0.1:3110`  
**Unit tests:** `pytest -q tests/test_m47_6_cors_policy.py` → **13 passed**

## Runtime matrix (Node fetch against managed BFF)

| Case | Result | Evidence |
|---|---|---|
| Allowed origin GET | ✅ | `Access-Control-Allow-Origin: http://127.0.0.1:3110` exact match; never `*` |
| Denied origin GET | ✅ | `http://evil.example:9999` → **no** ACAO |
| Missing origin | ✅ | no ACAO / not `*` |
| OPTIONS preflight allowed | ✅ | status 200; ACAO exact UI origin; methods GET,POST,PUT,PATCH,DELETE,OPTIONS,HEAD |
| OPTIONS preflight denied | ✅ | evil origin → no permissive ACAO |
| Credentials | ✅ | `Access-Control-Allow-Credentials: true` |
| Methods bounded | ✅ | no `*` in allow-methods |
| Headers bounded | ✅ | includes `Content-Type`, `x-baadar-session`; no `*` |
| Unsupported method TRACE | ✅ | TRACE not listed as allowed |
| Browser credentialed fetch to BFF health | ✅ | from Playwright page (same origin allowlist) |

## Production fail-closed

Covered by unit tests (`environment=production` + empty `SAATHI_CORS_ORIGINS` → empty allowlist). Not flipped to production during browser cert.

## What was not done

- No wildcard added to pass tests.
- Production origin list not modified.
- Always-on process on `:8765` was not treated as cert evidence (may predate M47.6 load).

## Classification

```text
CORS_RUNTIME = PASS
```
