# M32 — Provider Configuration & Endpoint Policy

Module: `saathi/connectors/providers/config.py`

## Model

`ProviderConfig` — secret-free, declarative:

- `provider_id`, `environment`, `endpoint_reference`
- `timeout_policy` (connect / read / total_deadline), `retry_policy`, `rate_limit_policy`
- `auth_profile`, `request_size_limit`, `response_size_limit`
- `allowed_operations`, `data_classification`, `side_effect_class`, `enabled`

## Fail-closed rules (`validate_config`)

- Production/live environments → `ConfigError` (`environment_disabled`). Permitted:
  `local`, `test`, `sandbox`, `dev`.
- Side-effect ceiling: only `NONE` / `READ_ONLY`. Anything else fails closed.
- Data classification ceiling: only `PUBLIC` / `INTERNAL`.
- Auth profile must be secret-free (`none` / `public` / `sandbox_none`).
- Endpoint policy:
  - `inprocess://` / `loopback://` → allowed (deterministic transport);
  - `http://` → allowed **only** for loopback hosts; external HTTP without TLS fails;
  - `https://` → allowed with a host;
  - any other scheme → fails closed.
- Unknown environment / classification / side-effect → fails closed.

## Caller cannot override

`caller_attempts_config_override(metadata)` returns the offending key for any of:
`endpoint`, `url`, `auth`, `authorization`, `timeout`, `retry`, `max_retries`,
`headers`, `connect_timeout`, `read_timeout`, `deadline_override`, … Callers can
never supply an endpoint, auth mechanism, timeout escalation, or retry escalation.

## Hard ceilings (clamped on construction)

`MAX_TIMEOUT_SECONDS=30`, `MAX_TOTAL_DEADLINE=30`, `MAX_RETRIES=3`,
`MAX_RESPONSE_BYTES=256KiB`, `MAX_REQUEST_BYTES=64KiB`, `MAX_CONCURRENCY=4`.
