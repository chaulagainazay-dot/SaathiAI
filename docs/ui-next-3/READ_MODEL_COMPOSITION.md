# READ_MODEL_COMPOSITION

`saathi-os/lib/command-read-model.js` + `useHybridCommand.js`

Sources:
- GET `/paper/accounts/{id}/command-snapshot` (ledger)
- GET `/paper/accounts/{id}/risk`
- GET `/paper/accounts/{id}/proposals`
- missions, agents, approvals, evidence, infra (existing)

Provenance: LIVE | DERIVED | STALE | UNAVAILABLE | ERROR | LOADING
Fixture only via `?fixture=` for browser cert.
