# M32 — Request Normalization

Module: `saathi/connectors/providers/normalization.py` (`normalize_request`)

## Guarantees

- Rejects unsupported operations (`operation ∉ allowed_operations`).
- Enforces field-count and serialized-size ceilings; oversized → `INVALID_REQUEST`.
- Rejects any caller-injection field, fail-closed: `headers`, `authorization`,
  `auth`, `endpoint`, `url`, `base_url`, `retry`, `retry_policy`, `max_retries`,
  `timeout`, `timeout_policy`, `connect_timeout`, `read_timeout`, `cookie`,
  `proxy`, `transport`, `rate_limit`, `x-api-key`, `api_key`, `bearer`,
  `credential`, `secret`, `token`.
- Normalizes values (bounded strings, bounded nesting, coerced scalars).
- Provider-specific payloads are produced **only inside** the adapter boundary —
  the normalized request is provider-neutral.

## Field sensitivity

`classify_field_sensitivity(key)` maps obvious sensitive names to `AUTH_SECRET` /
`PERSONAL` / `FINANCIAL`; `data_classification_permitted` fail-closes to reject
anything outside `PUBLIC` / `INTERNAL` for the M32 pilot.

## Request fingerprint

`idempotency.compute_request_fingerprint` derives a deterministic SHA-256 over the
material request (connector_id + provider_id + operation + account_link + payload),
**excluding** secret/volatile keys (tokens, timestamps, request ids). Reordering
keys does not change it; changing material content does.
