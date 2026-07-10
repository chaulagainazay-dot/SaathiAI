# SaathiOS Auto-Repair Loop

Production-safe autonomous repair. Detects, diagnoses, repairs, tests, verifies,
documents, and **locally** commits recoverable failures — never blindly, never
without evidence.

```
Failure signal → Intake → Evidence → Classify → Root cause → Policy
  → Rollback point → Patch plan → Patch apply → Focused tests → Full suite
  → Verify runtime → Regression guard → Secret scan → Local commit → Report
```

## Package layout (`saathi/repair/`)

| Module | Responsibility |
|--------|----------------|
| `incident.py` | `RepairIncident`, `RepairEvidence`, `PatchPlan`, enums, fingerprint |
| `secrets_scan.py` | secret pattern scanner + `redact()` (security floor) |
| `evidence.py` | read-only capture: git state, env **presence** (never values), server smoke, health |
| `classifier.py` | evidence → `FailureCategory` (+ confidence, subsystem, suspected files) |
| `policy.py` | category + confidence + attempts → `DIAGNOSE_ONLY / AUTO_REPAIR_ALLOWED / APPROVAL_REQUIRED / MANUAL_ONLY` |
| `rollback.py` | records HEAD as rollback ref; refuses if unrelated dirty work |
| `strategies.py` | vetted, mechanical, reversible transforms (the ONLY auto-applied code) |
| `test_selector.py` | subsystem/category → focused test targets |
| `verify.py` | pytest runner + parser, server smoke, regression guard (verification ladder) |
| `history.py` | JSON store, fingerprint attempts, escalation |
| `grounding.py` | anti-hallucination behaviour probes (execution-trace verification) |
| `loop.py` | `AutoRepairLoop` orchestrator; emits `repair.*` events |
| `cli.py` / `api.py` | operator CLI + authed `/api/v1/repair/*` routes |

## Failure classification

`IMPORT_ERROR, COLLECTION_ERROR, TEST_FAILURE, ASYNC_ERROR, ROUTING_ERROR,
INTENT_ERROR, CAPABILITY_NOT_REGISTERED, EXECUTION_BYPASS, CONNECTOR_AUTH_ERROR,
CONNECTOR_RUNTIME_ERROR, TOOL_RESULT_NOT_GROUNDED, AGENT_HALLUCINATION,
API_CONTRACT_MISMATCH, EVENT_BUS_ERROR, DATABASE_ERROR, CONFIGURATION_ERROR,
DEPENDENCY_ERROR, FRONTEND_BACKEND_MISMATCH, SERVER_STARTUP_ERROR,
SECURITY_ERROR, UNKNOWN`.

## Repair levels (safety model)

- **Level 0 Diagnose-only** — read-only; logs, traces, git state, root-cause report.
- **Level 1 Safe local** — edit source/tests, run tests, **local** commit. Never push/deploy/rotate/migrate/send/trade.
- **Level 2 Approval-required** — dependency upgrades, migrations, file moves, auth/permission/policy changes. Waits for explicit approval.
- **Level 3 Prohibited** — push, deploy, credential ops, send/delete email, trades, transfers, DB deletion, history rewrite, force-push, disabling security. Never autonomous.

## Auto-repairable vs not

Auto (vetted strategy + confidence ≥ 0.6): `IMPORT_ERROR`, `COLLECTION_ERROR`,
`ASYNC_ERROR`, `EVENT_BUS_ERROR`.
Approval: contract/db/config/capability/execution-bypass/intent/routing.
Manual: `CONNECTOR_AUTH_ERROR` (external credential — never patched as code),
`DEPENDENCY_ERROR`, `SECURITY_ERROR`.

## Verification ladder

focused failing tests → affected subsystem tests → full suite → server import →
route-count smoke. Success requires: **target failure recovered AND no new
regressions AND route count did not drop AND secret scan clean.** Otherwise the
patch is rolled back automatically.

## Stopping conditions

Secret risk · unsafe git state · production data risk · permission change ·
external credential/payment/deploy required · 2 failed attempts per fingerprint ·
confidence too low · unknown root cause. Limits: `max_attempts_per_incident=2`,
`max_files_per_auto_repair=8`, `max_patch_lines=400`, `max_runtime_minutes`
configurable. Limits escalate clearly — never hide incomplete work.

## Anti-hallucination

For task-execution failures the loop inspects the **execution trace**, not the
final text. No tool call → "the task was not executed." Missing connector auth →
"connector is not connected or authenticated." A connector call where none was
expected (pasted content / define/explain) is itself a failure.

## Observability

Events: `repair.incident.created, repair.evidence.collected, repair.classified,
repair.policy.decided, repair.rollback.created, repair.patch.started,
repair.patch.completed, repair.tests.focused.completed, repair.tests.full.completed,
repair.verified, repair.committed, repair.failed, repair.manual_required` — with
incident id, category, repair level, commit hash; secrets excluded.
