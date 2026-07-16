# SaathiOS Technical Debt / Known Gaps

## Environment-blocked (need user action — NOT debt)
- macOS Accessibility grant → native Finder/TextEdit actuation.
- Cloud connector credentials (Gmail/Calendar/Telegram) → live connector ops.
- Safe staging account → authenticated browser workflow.
- GUI app installs (LibreOffice/Blender/Kdenlive) → more harness apps.

## Real debt (actionable without approval)
- Engineering Orchestrator (M20.0) PILOT BUILT: governed supervision layer over coding agents
  (`saathi/engineering/`), disabled by default, mock pilot + Claude adapter scaffold, 61 tests.
  Remaining (deferred): Control Center status cell; live Claude write pilot under explicit
  approval; CI status adapter; multi-provider adapters; cost/token tracking; auto-scheduling of
  engineering backlog (must not become a second OS scheduler). Must not grow into an ungoverned
  coding agent or duplicate Mission Engine / run ledger.
- Scheduled graph mission recovery (M17.17) BUILT: scheduled/trusted-event graph-backed
  missions launch through the MissionEngine, resume through the EXISTING graph + recovery
  layers, and settle mission+occurrence exactly once; honest graph→mission→occurrence
  state map; deterministic recovered-mission idempotency; crash windows F/G reconciled;
  12 blocking scheduled_graph.* checks; 31 tests. Delegates to the MissionEngine ONLY (no
  execution shortcut, asserted); no new tables (one read-only helper). Remaining
  (deferred): additional crash windows beyond F/G are covered by design (per-record
  leases) but not each exhaustively unit-tested; a dedicated scheduled-graph CLI command
  set + Control Center cell wiring beyond coord.health() were NOT added this milestone
  (reuse existing mission/scheduler/graph/recovery CLI + the coord.health aggregate);
  automatic reconciliation is opt-in (no OS/cloud scheduler provisioned); production
  auto-scheduling, distributed/multi-region recovery, untrusted graph JSON, dynamic graph
  mutation, and public webhooks remain OUT. Trading Guardian stays disabled (integration +
  engine recovery modules carry no trading surface, asserted).
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
  engine. PARALLEL / branching DAGs: BUILT (bounded, acyclic) in M17.16 (see below).
  Remaining: untrusted spec-JSON ingestion (deferred). Pipeline retry/resume/
  checkpoint: BUILT in M17.15 (see below).
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
  Remaining (deferred): distributed/remote/cloud checkpoints, arbitrary user-authored
  pipeline JSON, automatic recovery of untrusted steps, cross-owner checkpoint reuse.
  Trading Guardian stays disabled (no trading surface in the recovery module).
- Bounded parallel/branching graph pipelines: BUILT (bounded, acyclic). M17.16 added a
  thin dependency-aware bounded executor (pipeline_graph.py) around the SAME
  PipelineRunner — one fork, N independent branches, one explicit join barrier. Every
  step still runs through _run_step → run_harness_action → independent verification.
  Additive ledger tables (pipeline_graph/pipeline_dependency/pipeline_branch/
  pipeline_step_claim; the graph IS a pipeline_run). Full pre-exec validation; bounded
  ThreadPoolExecutor (≤16 steps, ≤4 workers, ≤4 branch width, ≤1 fork, ≤1 join);
  fail-closed join; dependency-CLOSED checkpoint reuse on resume (reuses M17.15
  _validate_checkpoint); shared M17.15 retry; durable per-step claims for exactly-once
  + crash reclaim; mission build_graph integration (no duplicate mission); Control
  Center graph cell + attention; CLI (pipeline-graph-health + 6 admin-gated); 13 green
  blocking pipeline_graph.* manifest checks; 44 tests; live sqlite→(sqlite||sqlite)→zip
  diamond. No second engine/scheduler/DAG-engine/retry-framework/checkpoint-system/
  ledger. Remaining (deferred): cyclic/nested-fork graphs, dynamic graph mutation,
  untrusted graph JSON, distributed/remote/multi-region execution, work stealing,
  cross-owner branch delegation, partial-join success, production auto-scheduling.
  Trading Guardian stays disabled (graph layer has no trading surface — asserted).
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
- Harness registry persistence: BUILT (M17.18) + HARDENED (M17.19) + MULTI-WRITER
  (M17.20) + HEALTH CELL (M17.21). Bounded untrusted load; flock + revision CAS;
  Control Center Registry Health + CEO brief when unhealthy. 19 M17.21 + prior
  registry tests; 20 blocking `registry.*` checks. Remaining: multi-host/NFS
  consensus (out of scope), live critical-check re-run in health poll (proxy
  only), richer quarantine retention UX.
- Universal ExecutionGateway Phase 1: BUILT (M17.22). Durable execution records,
  state machine, digest-bound approval, connector/CLI/local/MCP path through
  `ExecutionGateway.submit`, evidence/security/ledger/CC/CEO integrations, 25
  tests, 5 blocking `execution.*` checks. Remaining migration: browser, n8n,
  LLM model gateway, Trading Guardian unification, multi-host federation,
  production durable queue beyond local SQLite.
- Memory conventions auto-learn dirt: FIXED (M17.18.1). `memory_reflector` no
  longer mutates curated `saathi/memory/conventions.md`; runtime notes go to
  `data/memory/learned_conventions.{md,jsonl}` (under gitignored `data/`). Agent
  loads curated + short learned slice. Remaining: optional human promotion UI/CLI
  from learned → curated; any historical auto-learned sections already in
  conventions.md stay until manually reviewed.
- Multi-user isolation only probe-tested, not exercised with concurrent users.
- legacy saathi/connectors (pre-M15) telegram adapter = transitional exception,
  not yet wrapped under the platform adapter.

## Deferred (large / premature)
- Workflow Intelligence engine (gated: needs more live-execution proof first).
- Cloud/multi-tenant deployment, worker fleet, billing.

- Governed browser via ExecutionGateway: FIRST SLICE BUILT (M17.23).
  GovernedBrowser + policy + fake/service adapter; high-risk approval; domain
  deny; injection isolation; CC/CEO metrics. Remaining: migrate agent_browser /
  computer_agent CDP to gateway-only, remove ungoverned BrowserService default,
  live interactive session adapter for click/type/submit on real pages.

## External Capability Program debt (2026-07-15)

- SES-000E still Draft L1; AC-001 cross-ref vs requirements incomplete historically.
- OpenMontage / claude-video adapters remain **stubs**. OpenJarvis concepts: M20.1 runtime + M20.2 governed local path exist (default-off). Residual: no global `llm.generate`/chat migration; streaming/NDJSON deferred; live Ollama generation not required for pilot green; ModelGateway chat-llm override still separate.
- Home MCP: alias duplicate `codebase-memory` / `codebase-memory-mcp` (same backend — documented in M17.25; optional human disable of alias); **headroom enabled but binary missing**.
- Continuum remains **BLOCKED_LICENSE** (M17.25); CodeFlow / Fincept / blotato-skills licenses unclear — pilot gates.
- Priority 2/3 services not installed (intentional); Traceway vs OpenObserve decision open.
- M18.2 delivered local-first index+CLI+hybrid retrieval; optional home alias cleanup and Continuum licence still open.
- Full-repo eval quality is good but not perfect (lexical ranking; embeddings optional local-det only).

## CI Critical Manifest (M19.6 — 2026-07-16)
- FIXED: Linux CI Critical Manifest false failures from env-coupled checks
  (studio quota vs free-disk, native summary key shape, multi-app ffmpeg
  requirements in tests + SQLITE-TWOAPP/JQ-THREEAPP probes). reliability.yml
  now installs ffmpeg/jq/sqlite3. Remaining: native AX tests still skip
  honestly off-macOS; full suite may still hit other optional-capability skips.
