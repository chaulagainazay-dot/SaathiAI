# M15.3 Data Model (reuses connectors.db + in-memory resilience)
account: + granted_scopes (tracked for real OAuth accounts; scope engine enforces
exact match when present). OAuthFlow (transient, no secrets): state/pkce/nonce/
requested+granted scopes. CircuitBreaker (in-proc, scoped connector:account:op).
RateLimiter (layered user/connector/account/operation). Error taxonomy: stable
category → retryable/user_action/operator_action, redacted detail.
