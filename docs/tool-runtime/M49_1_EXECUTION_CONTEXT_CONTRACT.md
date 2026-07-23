# M49.1 Execution Context Contract

`ToolExecutionRequest` fields: run_id, attempt, tool_id, tool_version, call_id,
idempotency_key, capability, arguments, requested_by, approval_reference,
deadline, parent_task_id, trace_id, timeout_sec.

`BoundedToolContext` exposes: identities, authority/side-effect strings, cancel_check,
deadline, secret **handles** only, event/evidence sinks, scratch.

Does **not** expose: raw secrets, unrestricted RunStore, DB, FS, subprocess, provider clients.
