# M28 Architecture — Canonical Connector Execution

## Purpose

Eliminate production-capable connector bypasses by enforcing one path:

```text
Caller
  → ToolIntent / ConnectorRequest
  → ExecutionGateway (UniversalBoundary)
  → connector family handler (M28)
  → GovernedConnectorRuntime (M27)
  → policy + side-effect class + approval + rollout
  → registered adapter
  → redacted ConnectorResult (bypass=false) + evidence
```

## Modules

| Module | Role |
|--------|------|
| `saathi/execution/gateway.py` | Public ExecutionGateway API |
| `saathi/execution/universal.py` | Boundary; default `connector` handler |
| `saathi/connectors/gov/gateway_bridge.py` | ToolIntent ↔ ConnectorRequest; `execute_via_gateway` |
| `saathi/connectors/gov/runtime.py` | Rollout, lifecycle, policy, adapter invoke |
| `saathi/connectors/gov/side_effects.py` | Deterministic side-effect classes |
| `saathi/connectors/gov/compat.py` | Legacy `manager.execute` shim |
| `saathi/connectors/gov/bypass_guard.py` | Static bypass scan |

## Distinctions

| Term | Meaning |
|------|---------|
| Registration | Manifest + adapter bound in registry |
| Readiness | Lifecycle READY/DEGRADED |
| Rollout | OFF/SHADOW/CANARY/ACTIVE/DRAINING |
| Execution authorization | Gateway + policy + side-effect + approval |
| Adapter execution | Only after all gates |
| Compatibility wrapper | Public API → canonical path + deprecation |
| Bypass | Production side effect without gateway/gov |

## Non-goals

* Live OAuth / SaaS accounts  
* Connector marketplace  
* Trading Guardian  
* Cloud inference enablement  
* Migrating every infrastructure driver  

## Default posture

```text
connector rollout = OFF
inference rollout = OFF
cloud fallback = disabled
Trading Guardian = UNCHANGED / UNENGAGED
```
