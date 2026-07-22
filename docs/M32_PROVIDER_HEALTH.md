# M32 — Provider Health & Readiness

Module: `saathi/connectors/providers/health.py`

## States (`ProviderHealthState`)

`UNKNOWN`, `HEALTHY`, `DEGRADED`, `RATE_LIMITED`, `AUTH_BLOCKED`, `UNAVAILABLE`,
`MISCONFIGURED`, `QUARANTINED`, `DISABLED`. Healthy set = `{HEALTHY, DEGRADED}`.

## Transitions (`ProviderHealthTracker`)

- success → `HEALTHY` (resets consecutive counters);
- timeout → `DEGRADED`;
- `429` → `RATE_LIMITED`;
- auth/authz/scope → `AUTH_BLOCKED`;
- provider-unavailable / connection → `UNAVAILABLE`;
- malformed → `DEGRADED`, then `QUARANTINED` at `MALFORMED_QUARANTINE_THRESHOLD` (3)
  consecutive malformed responses.

## Readiness (`compute_readiness`) — layers stay distinct

Readiness ANDs: provider config enabled, connector certification, provider
verification, provider health, account readiness, credential readiness, scope
sufficiency, operation capability, approval, rollout. Any single failure denies,
with a specific reason, and every layer is reported separately.

Invariants enforced by the layering:

- A healthy provider does **not** imply authorized execution.
- A linked account does **not** imply provider health.
- A certified connector does **not** imply provider compatibility.
- With rollout OFF, a fully-ready provider is still limited to
  SHADOW/SIMULATION (`ready_shadow_only`).
