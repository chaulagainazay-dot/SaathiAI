# M47.8 — Production Configuration Gate

## CORS contract (confirmed)

| Rule | Status |
|---|---|
| Development allowlist explicit (local UI/cert ports) | ✅ `cors_policy.py` |
| Test ports 3110/3112 included | ✅ |
| Unknown origins denied | ✅ unit + M47.7 runtime |
| Wildcard ACAO not used | ✅ wildcards stripped; never emitted |
| Credentialed requests bounded | ✅ `allow_credentials=True` + exact origin |
| Methods/headers bounded | ✅ no `*` |
| Production fail-closed without `SAATHI_CORS_ORIGINS` | ✅ empty allowlist for production/staging/canary |

## Production gate (deployment)

```text
PRODUCTION_DEPLOYMENT_BLOCKED_UNTIL_SAATHI_CORS_ORIGINS_CONFIGURED
```

Operators must set, for example:

```bash
export SAATHI_ENV=production
export SAATHI_CORS_ORIGINS=https://<actual-production-origin>
```

**Do not invent** the production origin value in this PR.

## Draft-exit impact

This gate **does not** block marking PR #2 ready for **code review**.

It **does** block any claim of production deployment readiness and any deploy action from this milestone.

## This milestone

- Did **not** set `SAATHI_CORS_ORIGINS` in production  
- Did **not** deploy  
- Did **not** weaken allowlist  
