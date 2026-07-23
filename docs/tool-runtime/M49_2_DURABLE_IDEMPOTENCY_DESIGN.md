# M49.2 Durable Idempotency Design

Store: SQLite `data/tool_runtime/idempotency.db` table `tool_idempotency`.

Fields: scope, key, fingerprint, tool_id, version, run_id, call_id, authority,
side_effect_class, status, attempt, result_json, error_code, timestamps, lease.

Statuses: RESERVED, IN_PROGRESS, SUCCESS_CONFIRMED, FAILURE_CONFIRMED,
CANCELLED_CONFIRMED, TIMEOUT_CONFIRMED, OUTCOME_UNKNOWN, REQUIRES_REVIEW.

API: begin / complete / fail_release / heartbeat / reconcile_stale.
