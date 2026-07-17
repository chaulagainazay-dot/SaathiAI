# M21.2 — Failure Taxonomy

**Module:** `saathi/inference/failure_taxonomy.py`

## Policy / hard (never soft fallback)

UNKNOWN_CALLER, PROVIDER_NOT_ALLOWED, MODEL_NOT_ALLOWED, CAPABILITY_NOT_SUPPORTED,  
PRIVACY_DENIED, COST_DENIED, CLOUD_DENIED, TOOL_DENIED, STREAMING_DENIED,  
AUTHORIZATION_DENIED, KILL_SWITCH_ACTIVE, PRODUCTION_CERTIFICATION_REQUIRED,  
INVALID_REQUEST, TRADING_ISOLATION, AUTHENTICATION_FAILED, PERMISSION_FAILED,  
CONTEXT_LIMIT_EXCEEDED, OUTPUT_LIMIT_EXCEEDED

## Soft / runtime (may retry or failover per flags)

PROVIDER_UNREACHABLE, PROVIDER_TIMEOUT, RATE_LIMITED, MODEL_NOT_FOUND,  
MALFORMED_RESPONSE, STRUCTURED_OUTPUT_FAILED, PROVIDER_INTERNAL_ERROR,  
LOCAL_RUNTIME_UNAVAILABLE, RESOURCE_EXHAUSTED, CIRCUIT_OPEN

## Conservative default

UNKNOWN_PROVIDER_ERROR: not retryable, not failover-eligible, may impact circuit.

## Auth note

Authentication failures are **hard** and **not** ordinary soft fallback (prevents concealing bad credentials). They **do** count toward circuit impact.

## Redaction

`redact_error_message` strips api_key/token/bearer patterns from operator messages.
