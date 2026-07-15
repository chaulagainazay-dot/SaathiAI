# M18.4 — Governed InsForge Migration Write Pilot

**Status:** `PILOT_APPROVED_GOVERNED_MIGRATION_WRITE`
**Depends on:** M18.3 read-only provider (`5bda42f`)
**Module:** `saathi/providers/insforge/migration*.py`
**Not production-ready.**

---

## Workflow

```text
structured ops → plan → preflight → approval (fingerprint-bound)
  → ExecutionGateway submit → provider write (allowlisted POST)
  → read-only verification → evidence + rollback guidance
```

## Supported operations (structured only)

| Op | Notes |
|----|--------|
| `create_table` | Named columns; allowed types only |
| `add_column` | **Nullable only** in pilot |
| `create_index` | Non-unique or unique (unique → elevated risk) |

**No raw SQL console.** Free-form SQL bodies are rejected.

## Denied

DROP / TRUNCATE / DELETE / UPDATE / INSERT · GRANT/REVOKE · RLS disable · extensions · multi-project · production `environment` · irreversible flag · privilege escalation · MCP passthrough · trade ops.

## Risk → approval

| Risk | Approval |
|------|----------|
| LOW | L3 |
| ELEVATED | L4 |
| PROHIBITED | denied |

## Preflight strength labels (honest)

| Label | Meaning |
|-------|---------|
| `LOCAL_POLICY_ONLY` | Parse + policy only (provider disabled / unreachable) |
| `PROVIDER_VALIDATED` | Local policy + successful schema GET |

This pilot does **not** claim `TRANSACTION_ROLLBACK_VERIFIED`.

## Config

| Env | Default | Role |
|-----|---------|------|
| `SAATHI_INSFORGE_ENABLED` | false | Master enable |
| `SAATHI_INSFORGE_WRITES_ENABLED` | false | Separate write gate |
| (M18.3 URL/key/timeouts) | — | unchanged |

## Disable

```bash
export SAATHI_INSFORGE_WRITES_ENABLED=0
export SAATHI_INSFORGE_ENABLED=0
```

## Trading Guardian

Unengaged. Migration approvals never authorize trading. Package bans exchange/broker identifiers.
