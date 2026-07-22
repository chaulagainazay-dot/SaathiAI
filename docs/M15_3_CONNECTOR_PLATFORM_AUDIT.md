# M15.3 Connector Platform Audit

## Start state
Commit b353f44→884c582 (M15.2). 1284 passed. SECURITY STAGING READY.

## Audit classification (per subsystem)
| subsystem | class |
|-----------|-------|
| M15 platform (models/registry/execution/store/adapters) | canonical |
| M15.1 API + funnel + migration | canonical |
| M15.2 red-team harness | canonical (extended) |
| legacy saathi/connectors (manager/adapters/telegram) | migrate (shim; telegram = transitional-exception, real Bot API) |
| ExecutionEngine ownership (M15.2 ISO-001 fix) | canonical — NOT weakened |
| OAuth / scope engine / circuit breaker / rate limiter / error taxonomy | new (M15.3) |
| live cloud connectors (gmail/gcal/gcontacts/telegram/publishing) | environment-blocked |
| local_fs/local_git | live tested |
| github/browser/sqlite | deterministic-test-only |

## Bypass paths
Direct-call scan over saathi/connectors/platform → 0 violations. Legacy
saathi/connectors/adapters/telegram.py is a recorded transitional-exception
(real Bot API), tracked in migration.py; not yet wrapped under the platform
adapter — flagged, not silently left.

## What M15.3 added (no parallel framework)
- Canonical scope+permission engine (exact match, reason codes), wired into the
  engine BEFORE approval; scope enforced for accounts that track scopes.
- OAuth 2.0 + PKCE lifecycle SM: state/redirect/user binding, scope-reduction
  detection, refresh-no-widen. Live token exchange/refresh env-blocked (injectable).
- Circuit breakers scoped connector:account:operation (one account failing does
  not trip the connector); layered rate limiting.
- Provider error taxonomy (stable categories, redacted detail).
- Live-validation framework (contract/deterministic/sandbox vs live_*; CI runs
  safe only; live credentials-gated) + honest verification matrix (configured != healthy != live-tested).
- Red-team expansion: 9 new attacks (29 total, 29/29 hold).

## Remediation
SECRETLEAK-001 (Bearer/token-shape redaction gap) found + fixed + regression-tested.

## Honest limits
Live OAuth, token refresh, live provider operations, webhook provider events, and
browser verification NOT executed (no credentials / no running IdP or provider).
Reported as environment-blocked; never claimed.
