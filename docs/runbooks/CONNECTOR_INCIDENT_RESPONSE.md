# Connector Incident Response Runbook (M15.3)

General: preserve evidence (audit + event records), contain, revoke, recover,
verify. Never paste raw secrets into tickets. All revocation via the platform.

## Leaked / suspected credential
1. Disable the account (`state=disabled`), then revoke (`state=revoked` + delete
   credential reference). 2. Rotate the secret at the provider. 3. Reconnect via
   OAuth. 4. Scan logs/reports/backups for the token shape (redactor covers
   Bearer/sk-/ghp_/xoxb-). 5. Record in audit.

## Refresh-token failure
Account → `refresh_failed`/`expired`. User reconnects. Refresh never widens scope
(OAuthFlow.refresh blocks). Check circuit breaker for the account.

## OAuth callback attack (state/redirect/wrong-user)
Callback fails closed (`invalid_callback`). Confirm no account created. Review
redirect-URI allow-list. No action executes.

## Webhook replay / bad signature
Rejected (`replay`/`bad_signature`). Rotate webhook secret if suspected. Events
are untrusted data — they never authorize actions.

## Wrong-account / cross-user execution attempt
Blocked at the engine (ownership check, M15.2 ISO-001). Review audit for the
caller. Regression: test_iso_001.

## Runaway retry / excessive rate limiting
Circuit breaker opens (connector:account:operation). Layered rate limiter returns
retry-after. Manual reset only when authorized.

## Uncertain side effect
Result stays `uncertain`, never auto-retried. Reconcile with the provider before
any retry; record the reconciliation outcome.

## Unauthorized scope expansion
OAuth exchange/refresh blocks scope expansion/widening. Reconnect with correct
scopes; verify granted vs requested.
