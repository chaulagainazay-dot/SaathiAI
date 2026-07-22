# M32 — Provider Quarantine

Module: `saathi/connectors/providers/quarantine.py`

## Scope

Provider-adapter quarantine is **distinct** from connector deprecation (M29/M30)
and credential quarantine (M31). It governs a single provider adapter.

## Triggers (`QUARANTINE_REASONS`)

`repeated_malformed_responses`, `redaction_failure`, `secret_exposure`,
`impossible_response_state`, `adapter_contract_violation`,
`repeated_authentication_anomalies`, `provider_identity_mismatch`,
`request_signing_mismatch`, `operator_action`, `critical_incident`. An unknown
reason is coerced to `critical_incident` (fail closed).

## Behaviour

- Blocks new provider calls (runtime denies with `provider_quarantined`).
- Preserves safe metadata (secret-shaped keys stripped).
- Never deletes credentials; never auto-revokes unrelated account links.
- Emits safe history events (`quarantined` / `recovered`).
- Requires **explicit** recovery (`recover(...)`) — never automatic.

The runtime auto-quarantines a provider after 3 consecutive malformed responses
(via the health tracker) and denies all subsequent calls until an operator
explicitly recovers it.
