# M49.1 Result Contract

`ToolExecutionResult`: tool_id, version, call_id, status, outcome_class, data, safe_message,
error_code, retryable, side_effect_confirmed, cancellation_confirmed, timeout_detected,
evidence_references, timestamps, events, adapter_invoked.

Output validated against manifest schema before success.
Malformed output cannot become SUCCESS_CONFIRMED.
