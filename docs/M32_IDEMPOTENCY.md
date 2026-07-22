# M32 — Idempotency

Module: `saathi/connectors/providers/idempotency.py`

## Request fingerprint

`compute_request_fingerprint` — deterministic SHA-256 over the material request
(connector_id, provider_id, operation, account_link_id, normalized payload).
Secret/volatile keys (tokens, timestamps, request/correlation ids) are excluded,
so a fingerprint never carries secret material and is stable under key reordering.

## Idempotency store

`IdempotencyStore.reserve(...)` returns one of:

- `new` — no live record for this scoped key;
- `replay` — same scoped key **and** same fingerprint → reuse the logical operation, **no new provider call**;
- `conflict` — same scoped key but a **different** material fingerprint → deny (`CONFLICT`).

The scoped key is `connector_id | provider_id | account_link_id | idempotency_key`,
so reuse **fails across** providers, connectors, and accounts. Expired records
(TTL elapsed) are treated as `new` (fail safe → fresh operation).

## Record fields

`idempotency_key`, `connector_id`, `provider_id`, `operation`,
`request_fingerprint`, `approval_fingerprint`, `account_link_id`,
`credential_ref_id` (marker only), `created_at`, `expires_at`, `status`,
`provider_request_id_safe`, `result_reference`. Secret material is never stored;
`to_dict` further scrubs any credential-shaped field.

## Runtime behaviour

Duplicate provider responses never duplicate logical state (a `replay` short-circuits
before any provider call). Non-idempotent operations require explicit provider
idempotency support to be retried; otherwise they never auto-retry.
