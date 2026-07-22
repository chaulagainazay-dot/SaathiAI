# M29 Architecture — Governed Connector Manifests, Identity, and Trust Registry

## Purpose

Complete the connector architecture by defining **what a connector is**:

```text
Static Manifest (identity)
  → Registry (register / resolve / trust)
  → ExecutionGateway (M28)
  → GovernedConnectorRuntime (M27)
  → policy + side-effect + approval + rollout
  → registered adapter only
```

## Modules (new / extended)

| Module | Role |
|--------|------|
| `saathi/connectors/registry/` | Trust, capabilities, validation, deps, docs CLI, builtins, persistence |
| `saathi/connectors/gov/models.py` | Extended `ConnectorManifest` |
| `saathi/connectors/gov/registry.py` | resolve/inspect/deprecate/duplicate fail |
| `saathi/connectors/gov/runtime.py` | Builtin identity from static manifests; resolve-only |
| `saathi/connectors/gov/gateway_bridge.py` | Registry resolve before execute |

## Does not reimplement

Runtime gate, rollout service, approval stores, evidence writers, event bus,
incidents, ExecutionGateway core, HTTP/MCP/browser/local adapters.

## Built-in connectors (static)

| ID | Trust | Adapter |
|----|-------|---------|
| gov.http | LOCAL_NETWORK | HttpAdapter |
| gov.mcp | LOCAL_SERVICE | McpAdapter |
| gov.browser | LOCAL_NETWORK | BrowserAdapter |
| gov.local_tool | LOCAL_SYSTEM | LocalToolAdapter |

## Default posture

```text
connector rollout = OFF
inference rollout = OFF
cloud fallback = disabled
Trading Guardian = UNCHANGED / UNENGAGED
no live SaaS / OAuth / API keys
```

## Non-goals (M29)

* Live Gmail, GitHub, Calendar, Slack, Discord, Binance, Stripe  
* OAuth credential flows  
* Cloud inference enablement  
* Trading Guardian engagement  
