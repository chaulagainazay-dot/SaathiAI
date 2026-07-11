# M15.1 Data Model (reuses connectors.db)
account(id, connector_id, owner, label, state, cred_ref_id, project_scope, enabled)
credential_ref(ref_id, connector_id, scope, backend, backend_key, status, expiry, ...)  # metadata only
execution(id, owner, connector_id, tool_id, status, input_hash, idempotency_key[unique], risk, evidence, errors)
approval(id, owner, tool_id, account_id, input_hash, risk, environment, target, status, used, max_uses, expires_at)
webhook_event(dedup_key[unique]), sync_job(cursor/page_token/checkpoint), rate_bucket, failure
No new tables; metrics() aggregates existing rows.
