# M61 — Attention Mutation APIs

`attention_states` table (per execution, tenant-scoped, versioned). Governed
transitions acknowledge → acknowledged, resolve → resolved, reopen → open via
`POST /workflow/attention/{id}/action` (ATTENTION_WRITE). Every mutation is audited
(`attention.acknowledge` / `.resolve` / `.reopen`) with actor + timestamp; optimistic
concurrency supported. The runtime execution itself is never altered — this is
operator triage metadata only. Was: BLOCKED (no API) → now SERVER_AUTHORIZED +
SERVER_AUDITED. Surfaced in the M60 attention detail page as a Triage panel.
