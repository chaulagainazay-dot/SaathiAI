# M29 — Connector Trust Model

## Trust levels

| Level | Meaning | Approval floor | ACTIVE eligible |
|-------|---------|----------------|-----------------|
| INTERNAL | In-process platform | L1 | yes |
| LOCAL_SYSTEM | Host tools / FS | L1 | yes |
| LOCAL_SERVICE | Local daemons / MCP runtime | L1 | yes |
| LOCAL_NETWORK | Loopback / LAN HTTP / browser policy | L2 | yes |
| EXTERNAL_SERVICE | Public SaaS (future) | L2 | yes |
| PRIVILEGED | High-impact financial/admin | L4 | **no** |
| PROHIBITED | Trading / forbidden | DENIED | no (OFF only) |

Trust is **registry-owned**. Callers cannot raise trust, lower approval floors,
or expand rollout eligibility.

## Capability ceilings

Capabilities cannot exceed trust:

| Trust | Allowed capability classes (ceiling) |
|-------|--------------------------------------|
| INTERNAL | READ, WRITE, EXECUTE, LOCAL_TOOL, FILESYSTEM, HTTP, MCP, BROWSER |
| LOCAL_SYSTEM | READ, WRITE, EXECUTE, LOCAL_TOOL, FILESYSTEM, HTTP |
| LOCAL_SERVICE | READ, WRITE, EXECUTE, LOCAL_TOOL, HTTP, MCP |
| LOCAL_NETWORK | READ, WRITE, HTTP, MCP, BROWSER, COMMUNICATE |
| EXTERNAL_SERVICE | READ, WRITE, HTTP, MCP, BROWSER, COMMUNICATE, ACCOUNT |
| PRIVILEGED | all classes (still policy + approval gated) |
| PROHIBITED | none |

`FINANCIAL` and `ACCOUNT` require elevated trust; trading remains PROHIBITED via
flags + side-effect policy (M28).

## Interaction with M28 side effects

Trust is identity. Side-effect class is per-operation at execute time.
Both must allow execution. Either may deny.

## Module

```text
saathi/connectors/registry/trust.py
saathi/connectors/registry/capabilities.py
```
