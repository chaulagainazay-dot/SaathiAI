# Auto-Repair Runbook

## CLI

```bash
.venv/bin/python -m saathi.repair.cli diagnose        # read-only: classify latest failure
.venv/bin/python -m saathi.repair.cli latest          # diagnose + attempt a SAFE repair
.venv/bin/python -m saathi.repair.cli incident <id>   # show a stored incident
.venv/bin/python -m saathi.repair.cli report <id>     # print repair report
.venv/bin/python -m saathi.repair.cli rollback <id>   # restore the rollback point (operator)
.venv/bin/python -m saathi.repair.cli history         # list repair history
```

## API (authenticated — `/api/v1/*` requires session, SAATHI_TOKEN, or local)

```
POST /api/v1/repair/diagnose      {source, command, stack_trace, failed_tests, ...}
POST /api/v1/repair/run           + {approve: bool}   # diagnose-only unless a strategy is wired
GET  /api/v1/repair/incidents
GET  /api/v1/repair/incidents/{id}
```

`/run` never pushes or deploys. Without a concrete strategy it stays
diagnose-only by design; Level-2 categories require `approve: true`.

## Programmatic

```python
from saathi.repair import AutoRepairLoop, RepairIncident
from saathi.repair.classifier import classify
from saathi.repair.strategies import ReexportSymbolStrategy

inc = RepairIncident(source="pytest",
                     stack_trace="ImportError: cannot import name X from pkg")
loop = AutoRepairLoop()
out = loop.diagnose(inc)          # Level 0
# Level 1 (only with a concrete, vetted strategy):
out = loop.run(inc, strategies=[ReexportSymbolStrategy("pkg/__init__.py", "sub", "X")])
print(out.to_dict())
```

## Reference scenario — "Analyze my email"

```python
from saathi.repair import verify_grounding
# generic director reply, Gmail never called:
verify_grounding("show my latest gmail", trace=[])
#   -> grounded=False, "connector not ... the task was not executed"
# missing credentials:
verify_grounding("show my latest gmail", trace=[], connector_authed=False)
#   -> CONNECTOR_AUTH_ERROR path -> MANUAL_REQUIRED, no code change
```

The loop classifies this as `EXECUTION_BYPASS` / `TOOL_RESULT_NOT_GROUNDED`
and — if credentials are missing — `CONNECTOR_AUTH_ERROR` (manual setup, working
code untouched). It never fabricates Gmail availability.

## Rollback

Each safe repair records the pre-repair HEAD as its rollback commit. To restore:
`saathi repair rollback <incident-id>` → `git reset --hard <rollback_head>`.
Automatic rollback also fires whenever verification/regression/secret-scan fails.

---

## Reliability modes (Repair 3 additions)

```bash
.venv/bin/python -m saathi.repair.cli inspect              # read-only env+failures analysis
.venv/bin/python -m saathi.repair.cli diagnose             # collection + critical manifest + server import
.venv/bin/python -m saathi.repair.cli repair --test <node> # targeted repair of one failing test
.venv/bin/python -m saathi.repair.cli loop --max-cycles 3  # bounded repair loop (1..10, never infinite)
.venv/bin/python -m saathi.repair.cli report               # latest journal + open known failures + baseline
.venv/bin/python -m saathi.repair.cli critical             # run critical regression manifest only
```

### Exit codes
`0` passed · `1` unresolved failures · `2` bad command/config · `3` unsafe worktree ·
`4` medium/high-risk needs review · `5` regression introduced · `6` infra failure ·
`7` max cycles reached unresolved.

### Quality records
- Critical manifest: `saathi/repair/critical_checks.json` (11 checks + server import)
- Baseline: `data/repair_baseline.json` — updated ONLY after full ladder success
- Known failures: `data/known_failures.json` — new/recurring/resolved/returned/signature-changed
- Journal: `artifacts/repairs/repair-<stamp>.{json,md}` — secret-redacted
- Policy: `saathi/repair/repair_policy.json` — limits, protected paths, risk rules

### BFF contracts (Repair 3)
- **CEO Home payload**: 14 required keys; `actions` is exactly 3 real navigable
  cards, FINANCE ranked first (standing daily review, real pending count).
- **dreamPct canonical**: `saathi.financial_mission_control.dream_progress_pct`
  — PERCENTAGE (1.0 == 1% of DREAM_TARGET), 4 dp, negatives→0, zero/invalid
  target→0.0, >100 allowed. DI rule: explicit `Signals` drive the payload;
  no Signals → real recorded revenue.

### CI
`.github/workflows/reliability.yml` — collection check, server import +
route-count floor, critical manifest, full suite, report artifacts.
Diagnose-only: CI never commits or pushes code changes.
