# M47.6 — BFF CORS Contract

**Date:** 2026-07-23  
**Module:** `saathi/cors_policy.py` · applied in `saathi/server.py`

## Rules

1. **No wildcard** `*` in allowlist when credentials are enabled.  
2. **Production / staging / canary fail closed** if `SAATHI_CORS_ORIGINS` is unset → empty allowlist.  
3. **Development defaults** include documented UI ports: 3000, 3100, 3110, 3112 (localhost + 127.0.0.1) and 8765.  
4. **Methods** bounded: GET, POST, PUT, PATCH, DELETE, OPTIONS, HEAD.  
5. **Headers** bounded: Accept, Content-Type, Authorization, x-baadar-session, etc.  
6. **Credentials:** `allow_credentials=True` (session cookie / header flows).  

## Configuration

```bash
# Production (required)
export SAATHI_ENV=production
export SAATHI_CORS_ORIGINS=https://app.example.com

# Development (optional override)
export SAATHI_CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3110
```

## Tests

`tests/test_m47_6_cors_policy.py` — parse, resolve, deny wildcard, fail-closed prod, origin allow/deny.
