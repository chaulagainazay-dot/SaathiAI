# M49.3 Event Completion

Canonical events emitted by ToolExecutionService include requested, validated, approval_validated, started, completed/failed/cancelled/timeout/blocked/outcome_unknown.

Guarantees:
- one terminal outcome class per call
- no success before output validation
- no cancellation success without confirmation
- redacted payloads
