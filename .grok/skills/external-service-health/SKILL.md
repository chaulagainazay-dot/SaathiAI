---
name: external-service-health
description: >
  Health, resource, and failure-isolation checks for SaathiOS external services
  and MCP pilots. Use when starting/stopping pilots, measuring 8 GB Mac impact,
  verifying disable switches, or recording ON_DEMAND vs ALWAYS_ON classification.
---

# External Service Health

## Resource classes (required on every pilot)

| Class | Meaning |
|-------|---------|
| `ON_DEMAND_LOCAL` | Start for task, stop after; preferred on 8 GB Mac |
| `ALWAYS_ON_REMOTE` | Hosted elsewhere; not on laptop |
| `OPTIONAL_EXPERIMENT` | Lab only; never production default |
| `NOT_SUITABLE_FOR_8GB_MAC` | Do not run continuously locally |

## Pre-flight (every service milestone)

```bash
# document at start and after load
vm_stat | head -20
sysctl hw.memsize
df -h .
```

Record: idle memory, active memory, CPU, disk, startup time, shutdown behavior, background services, retained data, cache growth.

## Health contract

Every pilot must expose:

1. **Health endpoint or CLI** returning ok/degraded/fail without secrets.
2. **Disable switch** (env flag, compose profile, or MCP `enabled = false`).
3. **Failure isolation** — service down must not crash SaathiOS core APIs.
4. **Timeouts** on all outbound calls.
5. **Redacted logs** — no tokens, cookies, or private payloads.

## MCP health

- Prefer project `.grok/config.toml` for project-scoped MCP (requires trust).
- Document home-level MCP in `docs/integrations/MCP_PROJECT_INVENTORY.md`.
- Broken `enabled = true` entries (missing binary) are a security hygiene defect.

## SaathiOS hooks

- Prefer Evidence + SecurityStore events when side effects occur.
- Connector/MCP risk floor: `saathi/connectors/platform/mcp.py` clamps untrusted tools.

## Do not

- Run Traceway + OpenObserve as dual authorities.
- Mount FileBrowser on `$HOME`.
- Enable Versus detect mode without training/shadow first.
- Claim health from mocks alone.
