# M32 — Provider Adapter Contract

Module: `saathi/connectors/providers/contract.py`

## Canonical interface

`ProviderAdapter` (ABC) — every provider adapter implements exactly these methods:

| Method | Responsibility |
|--------|----------------|
| `prepare(config)` | Bind validated `ProviderConfig`. Must NOT fetch secrets or open live sessions. |
| `validate_request(ctx)` | Validate a normalized request; raise on injection / unsupported / oversize. |
| `execute(ctx) → ProviderAdapterResult` | One bounded provider attempt; return a normalized result. |
| `normalize_response(raw) → dict` | Turn a raw provider response into safe provider-neutral data. |
| `classify_error(exc) → str` | Map a raw error to a canonical `ProviderErrorCode`. |
| `health() → str` | Local `ProviderHealthState` probe (no authority). |
| `capabilities() → tuple[str,…]` | Supported operations. |
| `close()` | Release adapter-local resources. |

`adapter_satisfies_contract(adapter)` returns `(ok, missing_methods)`; a broken
adapter fails closed at the runtime boundary (`INTERNAL_ADAPTER_ERROR`).

## Authority is outside the adapter

`determines_authority()` and `can_activate_rollout()` are **final** and always
`False`. The adapter cannot:

- determine execution authority (policy / approval / ExecutionGateway / rollout own it);
- activate connector rollout;
- retrieve undeclared credentials;
- mutate connector certification (M30);
- mutate provider verification during an eligibility read (M32).

## Input / output types

- `ProviderExecutionContext` — connector_id, provider_id, operation, request_id,
  idempotency_key, deadline, approved_capabilities, account_link, credential_lease,
  safe_metadata, payload, mode.
- `ProviderAdapterResult` — status, provider_request_id_safe, normalized_data,
  safe_metadata, rate_limit, latency_ms, retryability, side_effect_class,
  evidence_refs, limitations, error_code, safe_message, attempts, mode,
  `authoritative` (always False for SHADOW/SIMULATION), request_fingerprint.

## Pilot adapter

`EchoProviderAdapter` (`adapters/echo_provider.py`) — bound to connector `gov.http`
and provider `saathi.echo.v1`, READ_ONLY, backed by the deterministic simulator.
One provider attempt per call: transport failures propagate (runtime classifies +
decides retries); HTTP-status conditions normalize into a canonical error result.
