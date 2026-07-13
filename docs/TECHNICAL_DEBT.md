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
  engine. Remaining: PARALLEL / branching DAGs, pipeline retry/resume/checkpoint,
  scheduling, and untrusted spec-JSON ingestion (all deferred).
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
- Harness registry persistence (data/application_harnesses/registry.json) written
  but not loaded on boot (in-memory bootstrap only).
- Multi-user isolation only probe-tested, not exercised with concurrent users.
- legacy saathi/connectors (pre-M15) telegram adapter = transitional exception,
  not yet wrapped under the platform adapter.

## Deferred (large / premature)
- Workflow Intelligence engine (gated: needs more live-execution proof first).
- Cloud/multi-tenant deployment, worker fleet, billing.
