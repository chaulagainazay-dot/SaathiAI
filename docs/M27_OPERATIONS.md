# M27 Operations

```bash
# Bootstrap built-in governed connectors
.venv/bin/python -m saathi.connectors.gov bootstrap
.venv/bin/python -m saathi.connectors.gov status
.venv/bin/python -m saathi.connectors.gov list
.venv/bin/python -m saathi.connectors.gov mode OFF
.venv/bin/python -m saathi.connectors.gov mode SHADOW

# ACTIVE requires production_certified=true
.venv/bin/python -m saathi.connectors.gov mode ACTIVE

# Execute (mode must allow)
.venv/bin/python -m saathi.connectors.gov exec gov.mcp health
.venv/bin/python -m saathi.connectors.gov exec gov.local_tool python_version
```

## Evidence

```text
docs/evidence/m27/connector_events.jsonl
docs/evidence/m27/evidence_*.json
docs/evidence/m27/incidents.json
```

## Disable

```bash
.venv/bin/python -m saathi.connectors.gov mode OFF
# or registry disable per connector in code/tests
```

## Relation to M26

Connector runtime inherits rollout modes. Inference ops remain separate:
`python -m saathi.inference.ops`.
