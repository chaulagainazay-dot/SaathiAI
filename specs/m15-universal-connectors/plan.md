# M15 Plan

Subpackage `saathi/connectors/platform/` (existing `saathi/connectors/` and
`saathi/infrastructure/connectors/` kept; migration documented, no breakage).
Governance in `saathi/specs/` + `.specify/`. Reuse ExecutionGateway (M-exec),
M9 memory, M10 agents. Local commits only. Evidence separated by honesty class.

Files: models.py, catalog.py, credentials.py, adapters.py, store.py,
registry.py, execution.py, health.py, webhook.py, sync.py, mcp.py, __init__.py;
saathi/specs/{__init__,traceability,cli}.py; specs artifacts; tests.
