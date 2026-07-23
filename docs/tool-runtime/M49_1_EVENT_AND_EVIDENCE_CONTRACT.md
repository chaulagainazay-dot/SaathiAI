# M49.1 Event and Evidence Contract

Events: tool.requested, tool.validated, tool.blocked, tool.started, tool.completed,
tool.failed, tool.cancellation_*, tool.timeout_detected, tool.outcome_unknown, tool.evidence_recorded.

One terminal event; payloads redacted; ordered in result.events list.
Optional event_recorder bridges to RunStore.event when called from AgentExecutor.
