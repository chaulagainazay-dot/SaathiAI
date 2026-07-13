# SaathiOS Technical Debt / Known Gaps

## Environment-blocked (need user action — NOT debt)
- macOS Accessibility grant → native Finder/TextEdit actuation.
- Cloud connector credentials (Gmail/Calendar/Telegram) → live connector ops.
- Safe staging account → authenticated browser workflow.
- GUI app installs (LibreOffice/Blender/Kdenlive) → more harness apps.

## Real debt (actionable without approval)
- Long-running harness task control: cancel + orphan-free timeout kill +
  live-enforced resource limits BUILT & live-proven (M17.8). Durable run tracking
  upgraded from the single-process JSONL journal to a **transactional SQLite run
  ledger** (M17.9, run_ledger.py): CAS state machine, one-claimant-per-run,
  terminal immutability, ownership-safe cancel, exactly-once idempotent crash
  recovery, heartbeats + stuck-run classification, recovery ops, safe reversible
  JSONL migration, admin-maintenance CLI (OS-identity, audited — no caller-supplied
  identity trusted), Control Center read model, and a dedicated green blocking
  Critical Manifest entry. Multi-PROCESS concurrency proven (spawn, not threads).
  Remaining: pause/resume/checkpoint (contract_ready only — process suspension is
  NOT application checkpointing); multi-user LOAD (vs. cross-user gates); a
  production monitoring/alerting dashboard on top of the ledger read model.
- Production monitoring/alerting: SUBSTRATE + DELIVERY BUILT. M17.10 added
  deterministic dedup stuck-run alerting; M17.11 added durable, deduplicated,
  retryable notification DELIVERY (run_alert_delivery table, bounded deterministic
  retry to terminal_failed, restart-safe, concurrency-safe lease claims, one
  credential-free local transport, deterministic policy with resolve/ack
  suppression), an opt-in interval scheduler adapter (default disabled), event-bus
  evidence, Control Center delivery health, admin-audited retry, and 7 green
  blocking manifest entries. Remaining: EXTERNAL transports (Telegram/email/Slack/
  PagerDuty — fail-closed stubs today), production/auto scheduling, escalation
  policy, and an incident-response drill.
- Multi-harness pipeline: FIRST SLICE BUILT. M17.12 added a governed SEQUENTIAL,
  fail-closed orchestrator (pipeline.py) composing the sole run_harness_action per
  step, additive pipeline_run/pipeline_step ledger tables, one confined workspace
  with pre-execution path-escape rejection + artifact wiring, honoured approval
  gates (no silent elevation), owner-safe records, Control Center attention, a LIVE
  sqlite→zip chain, and 7 green blocking manifest entries. No second execution
  engine. Remaining: PARALLEL / branching DAGs and untrusted spec-JSON ingestion
  (deferred). Pipeline retry/resume/checkpoint: BUILT in M17.15 (see below).
- Pipeline retry/resume/checkpoint: BUILT. M17.15 added governed recovery around the
  existing PipelineRunner + ledger — additive pipeline_checkpoint + pipeline_recovery
  tables, checkpoint-on-verified-success, deterministic step/dependency/artifact
  fingerprints, contiguous-valid-prefix reuse with artifact-integrity + confinement
  checks, category-allowlisted bounded retry, approval-safe (increased risk invalidates
  reuse; resume stops at approval_required; no force-success), lease-based recovery
  claiming, crash reconciliation (uncertain → stop_uncertain), a governed bounded
  reopen_pipeline (the sole exception to pipeline terminal immutability), mission
  integration (no duplicate mission), Control Center attention, 8 CLI commands, and 9
  green blocking manifest checks. No second engine/retry framework/verification path.
  Remaining (deferred): PARALLEL/branching DAG recovery, distributed/remote/cloud
  checkpoints, arbitrary user-authored pipeline JSON, automatic recovery of untrusted
  steps, cross-owner checkpoint reuse. Trading Guardian stays disabled (no trading
  surface in the recovery module).
- Autonomous mission engine: FIRST SLICE BUILT. M17.13 added a layer ABOVE the
  pipeline (mission.py MissionEngine) — a Mission carries one business objective +
  strongly-typed validated params + an approval requirement + a template ref and
  DELEGATES to the M17.12 PipelineRunner (never executes tools). Additive
  mission/mission_run ledger tables, explicit fail-closed state machine with
  immutable terminals, owner isolation, honoured approval gates (no elevation),
  fail-closed (completed only if the pipeline succeeded), retry-as-new-instance,
  Control Center attention (failed + approval_required), 6 CLI commands, a LIVE
  delegated sqlite→zip mission, and 7 green blocking manifest entries. No second
  execution engine / trust model / DB / scheduler. Remaining (deferred):
  untrusted mission-spec JSON ingestion, LIVE scheduling + event/triggered
  execution (recurrence is instance-per-occurrence only; no cron/launchd wired),
  PARALLEL missions, and multi-user LOAD. NOTE: distinct from the older
  saathi/missions/ business-content package (untouched).
- Mission scheduler + trusted event triggers: FIRST SLICE BUILT. M17.14 added the
  WHEN layer ABOVE the MissionEngine (scheduler.py + event_triggers.py) — schedules
  (one_time/interval/daily/weekly), durable occurrences (one per due time, unique
  dedup key), deterministic mission ids (one mission per occurrence), lease-based
  claiming, restart reconciliation, infra-only bounded retry, a trusted internal
  event allowlist with receipt dedup, an opt-in interval runner (default OFF),
  Control Center attention, 12 CLI commands, and 8 green blocking manifest checks.
  Delegates to the MissionEngine ONLY (no execution shortcut — asserted). No second
  scheduler DB / job runner / execution engine. Remaining (deferred): CRON
  expressions, arbitrary PUBLIC WEBHOOK ingestion, UNTRUSTED JSON mission
  definitions, DISTRIBUTED / multi-region scheduling, PARALLEL mission execution, NL
  calendar parsing, external SaaS schedulers, and PRODUCTION AUTO-SCHEDULING (the
  interval runner is opt-in; no OS launch agent / cron / cloud job is provisioned).
  Trading Guardian stays disabled (scheduler/event modules carry no trading surface).
- Harness registry persistence (data/application_harnesses/registry.json) written
  but not loaded on boot (in-memory bootstrap only).
- Multi-user isolation only probe-tested, not exercised with concurrent users.
- legacy saathi/connectors (pre-M15) telegram adapter = transitional exception,
  not yet wrapped under the platform adapter.

## Deferred (large / premature)
- Workflow Intelligence engine (gated: needs more live-execution proof first).
- Cloud/multi-tenant deployment, worker fleet, billing.
