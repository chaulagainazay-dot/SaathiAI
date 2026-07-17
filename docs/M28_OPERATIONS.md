# M28 Operations

```bash
# Status (mode OFF by default)
.venv/bin/python -m saathi.connectors.gov bootstrap
.venv/bin/python -m saathi.connectors.gov status
.venv/bin/python -m saathi.connectors.gov mode OFF

# Shadow evaluation (no external side effects)
.venv/bin/python -m saathi.connectors.gov mode SHADOW
.venv/bin/python -m saathi.connectors.gov exec gov.mcp health

# Bypass report
.venv/bin/python -m saathi.connectors.gov.bypass_guard
```

## Evidence

```text
docs/evidence/m28/connector_migration_ledger.json
docs/evidence/m28/connector_bypass_report.json
docs/evidence/m28/deprecation_events.jsonl
docs/evidence/m27/  (runtime evidence still written here + m28 schema fields)
```

## Disable

```bash
.venv/bin/python -m saathi.connectors.gov mode OFF
```

Do **not** set CANARY/ACTIVE on the real host during M28 without operator authorization.
