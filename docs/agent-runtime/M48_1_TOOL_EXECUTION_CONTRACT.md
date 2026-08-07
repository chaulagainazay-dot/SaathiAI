# M48.1 — Tool Execution Contract

## Canonical path

```text
Agent / Orchestrator
  → policy.check_tool(agent, tool)
  → ToolIntent (immutable)
  → ExecutionGateway (validate → authorize → risk → approve → execute → sanitize → evidence)
  → SanitizedResult + Evidence
```

**No tool side effects bypass ExecutionGateway.**

## Tool identity fields

| Field | Source |
|---|---|
| tool name | string id (e.g. `file.read`) |
| risk | policy `_TOOL_RISK` → RiskClass |
| allow/deny | AgentDefinition lists |
| approval | risk ≥ LOCAL_MUTATION or agent.requires_approval |
| timeout / cancel | gateway + run cancel |
| retry | transient-only policy |
| redaction | ResultSanitizer / secret redaction tests |
| evidence | ExecutionResult.Evidence |

## Safety rules

- Allowlist / denylist enforced  
- Strict validation fail-closed  
- Bounded output / sanitization  
- Timeouts and cancellation  
- No blind retry of non-idempotent external mutation  
- No credential logging  
- Unknown tool not faked (`test_unknown_tool_not_faked`)
