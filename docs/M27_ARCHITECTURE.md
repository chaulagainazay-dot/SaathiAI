# M27 Architecture — Governed Connector Framework

## Purpose

One **canonical** governed path for external connector communication, reusing
M21–M26 governance without adding live SaaS accounts.

## Canonical module

```text
saathi/connectors/gov/
  models.py      lifecycle + manifest + request/result
  policy.py      allow/deny domains, operations, payload secrets
  auth.py        env/local secure *references* only
  registry.py    register / validate / ready / disable / recover
  runtime.py     single execute path
  redaction.py   reuses mcp_governance redaction
  adapters/
    http.py      GET/POST/PUT/PATCH/DELETE (injectable transport)
    mcp.py       reuses mcp_governance
    browser.py   reuses saathi.browser policy
    local_tool.py allowlisted commands only
```

## Does not replace

| Existing | Role remains |
|----------|----------------|
| ExecutionGateway | ToolIntent universal boundary |
| infrastructure/connectors | Driver registry for product adapters |
| connectors/manager | Account-scoped catalog execute |
| mcp_governance | MCP policy authority |
| browser/* | Browser domain/production adapters |
| inference/ops | Rollout modes + incidents |

M27 **governs** connector kinds through `GovernedConnectorRuntime`; legacy
surfaces stay for compatibility and should migrate over time.

## Execute flow

```text
ConnectorRequest
  → rollout mode (OFF/SHADOW/CANARY/ACTIVE/DRAINING)
  → lifecycle (READY/DEGRADED/…)
  → production_certified (ACTIVE only)
  → ConnectorPolicy (domain/op/payload)
  → approval token (mutations)
  → auth resolution (names only)
  → rate limit
  → adapter.execute
  → redacted evidence + events
  → incident on failure (deduped)
```

## Built-in connectors (no live accounts)

| ID | Kind |
|----|------|
| gov.http | HTTP |
| gov.mcp | MCP policy |
| gov.browser | Browser policy |
| gov.local_tool | Allowlisted local |

## Ownership / non-goals

* No cloud inference enablement  
* No API keys in repo  
* No live OAuth  
* Trading connectors forbidden  
* Default rollout **OFF**  
