# M17.13 Validation — Autonomous Mission Engine

Start/rollback point: HEAD `186a72f` (M17.12). Branch `milestone/m7-security-engine`.
Verdict: **AUTONOMOUS MISSION ENGINE STAGING READY** (not production).

## What was built
A layer ABOVE the pipeline. A **Mission** = one business objective (today's IELTS
lesson, daily CEO brief, kitchen inventory audit …) carrying strongly-typed
validated parameters, an approval requirement, and a reference to a reusable
**template**. The hierarchy is now:

```
Mission → Pipeline → Harness Step → Adapter → Verification → Ledger
```

A Mission **never executes a tool**. It DELEGATES to the existing M17.12
`PipelineRunner`, which composes the sole governed `service.run_harness_action` per
step (ownership → trust → risk/approval → the sole adapter → INDEPENDENT
verification → durable ledger). No second execution engine, trust model, DB,
scheduler, or approval path was added.

### Deliverables
- **Ledger** (`run_ledger.py`): additive `mission` + `mission_run` tables in the
  SAME ledger DB. `mission` PK-unique; `mission_run` UNIQUE(mission_id, attempt).
  Explicit fail-closed state machine
  `draft → (approval_required|approved) → queued → running →
  {completed|failed|cancelled|blocked}`; terminals immutable; owner-safe field
  projections; params secret-rejected on write and stored as owner-safe JSON.
  Methods: `create_mission`, `approve_mission`, `mark_mission_approval_required`,
  `enqueue_mission`, `begin_mission_run`, `finish_mission_run`, `cancel_mission`,
  `block_mission`, `inspect_mission`, `list_missions`, `mission_history`,
  `mission_health`. `health()` census extended with a `missions` count.
- **Engine** (`mission.py`): `MissionEngine` (create/approve/enqueue/run/launch/
  cancel/block/retry/inspect/list/history/health), `validate_params` (strong typed
  coercion, required checks, enum bounds, unknown-key rejection, bool≠int),
  `MissionTemplate` / `MissionParameter`, and a shipped trusted default template
  `data_bundle` (the proven sqlite→zip chain as one objective).
- **Control Center** (`aggregator.py`): owner-safe `missions` + `mission_health`
  in the harnesses cell; `_attention` folds failed missions (`harness_mission`,
  high) and approval_required missions (medium).
- **CLI** (`cli.py`): `mission-health` (always-on census) + admin-gated
  `missions`, `mission-inspect`, `mission-history`, `mission-run`, `mission-retry`
  (verified OS identity; `mission-run` launches under the mission's OWN owner and
  halts an approval-required mission at approval_required).
- **Ops**: 7 dedicated BLOCKING critical-manifest checks (`mission.*`).
- **Tests**: `tests/test_m17_13_mission_engine.py` (32).

## Evidence
- New tests: **32 passed** (`test_m17_13_mission_engine.py`).
- Harness lineage + Control Center regression (`m17_13`, `m17_12`, `m17_9`,
  `m17_3`, `m16_control_center`): **116 passed**.
- Full suite: **1687 passed / 1 skipped / 0 failed** (+32 over the 1655 baseline).
- Mission critical checks load: 7 blocking `mission.*` entries via manifest runner.
- `git diff --check`: clean. Secret scan over M17.13 files: 0 matches.
- Live CLI smoke: `mission-health` returns a census with no admin; `missions`
  without `SAATHI_HARNESS_ADMIN=1` returns rc 3 (admin gate).

## Security properties proven (deterministic tests)
- **Owner isolation**: run/enqueue/approve/cancel/retry/inspect/list all reject an
  owner mismatch and never execute.
- **Approval honesty**: an approval-required mission cannot be queued or run until
  explicitly approved; unapproved enqueue moves it to `approval_required` (no silent
  elevation). The per-step risk gate inside `run_harness_action` still applies
  independently underneath.
- **Fail-closed / no partial success**: a mission is `completed` ONLY if its
  delegated pipeline succeeded; a pipeline failure, a template exception, a
  no-steps template, or a missing template drives it to `failed`.
- **Parameter validation before execution**: unknown keys, missing required,
  bad type, and out-of-range enum are rejected before any pipeline runs.
- **Immutable terminals + fail-closed transitions**: terminal missions reject
  further transitions; unlisted transitions are rejected; `begin_mission_run` only
  fires from `queued` (no double-run).
- **Retry discipline**: retry is rejected for any non-failed mission; a failed
  retry CLONES a new instance correlated to its parent (terminal stays immutable).
- **Owner-safe records**: no argv/output/sql/secrets in mission or history records
  (params are secret-rejected on write).
- **Concurrency**: multi-process concurrent create dedups to exactly one winner.

## Boundaries preserved
No existing milestone regressed. No bypass of `run_harness_action`, approval gates,
verification, Trading Guardian, ownership boundaries, or the ledger. The Control
Center and `pipeline.py` were extended, not replaced. Trading Guardian not engaged
(no financial/external execution; approval gates strengthened, never bypassed).

## Deferred (documented, not pretended)
Untrusted mission-spec JSON ingestion; LIVE scheduling + event/triggered execution
(recurrence is instance-per-occurrence only — no cron/launchd/event trigger wired);
parallel missions; multi-user LOAD.
