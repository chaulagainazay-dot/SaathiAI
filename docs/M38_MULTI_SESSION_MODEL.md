# M38 — Multi-Session Model

## Isolation

* Independent session IDs and correlation IDs
* No shared SecretHandle objects
* No plaintext secrets in coordinator state
* Per-session call budgets + aggregate budget
* Concurrency ceiling (default 2, hard max 4)
* One failure does not revoke unrelated sessions

## Metadata retained

provider_id, credential_ref_id, non-reversible fingerprint, authorization id,
call budget, state, cleanup state, retry counts — never secrets or auth headers.
