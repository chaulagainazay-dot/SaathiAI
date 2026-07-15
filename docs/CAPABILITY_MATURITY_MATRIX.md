# SaathiOS Capability Maturity Matrix (as of HEAD 0a77882)

Levels: implemented < deterministic-tested < security/red-team-tested < live-tested < production.

| capability | maturity | evidence |
|-----------|----------|----------|
| ExecutionGateway / approval binding | live+red-team | M15/M15.2 gateway-routed, 78/78 red-team |
| Universal ExecutionGateway (Phase 1 boundary) | deterministic-tested | M17.22 submit path, states/idempotency/approval/retry, connector via gateway, 25 tests, +5 checks |
| Governed browser actions via ExecutionGateway | deterministic-tested | M17.23 domain/risk/approval/idempotency/injection isolation, 46 tests, +6 checks; residual ungoverned open() |
| Connector platform (local git/fs) | live-tested | M15.1 real local execution |
| Connector platform (cloud gmail/gcal/telegram) | environment-blocked | no credentials |
| Browser agent (Chrome CDP) | live-browser-tested | M17.1 real workflow |
| Native macOS (enumeration/identity/screenshot) | live-desktop-tested | M17.2 real NSWorkspace/screencapture |
| Native macOS actuation (Finder/TextEdit) | permission-blocked | AXIsProcessTrusted=False |
| Application harness — FFmpeg (media) | live-application-tested | M17.3/M17.4 transcode+verify |
| Application harness — SQLite (database) | live-application-tested | M17.5 schema/query/mutation+integrity |
| Application harness — jq (JSON transform) | live-application-tested | M17.6 transform+json verify |
| Application harness — zip (archive packaging) | live-application-tested | M17.7 pack+ZIP-slip/zip-bomb verify (live hostile archive) |
| Application harness registry persistence (load-on-boot) | deterministic-tested | M17.18 persist+reload, fail-closed, 15 tests, 5 blocking checks |
| Harness registry untrusted persistence hardening | deterministic-tested | M17.19 envelope/limits/atomic write/shared validator, 38 tests, +5 checks |
| Harness registry multi-writer concurrency | deterministic-tested | M17.20 flock+revision CAS+idempotency, 33 tests, +5 checks; single-host |
| Control Center registry health cell | deterministic-tested | M17.21 score/status cell + CEO brief gate, 19 tests, +5 checks |
| Control Center execution gateway cell | deterministic-tested | M17.22 metrics cell + attention + CEO gated summary |
| Memory conventions split (curated vs runtime learned) | deterministic-tested | M17.18.1 reflector writes data/memory only; recent-tail load; 10 tests; full suite green |
| Application harness — GUI apps (LibreOffice/Blender/Kdenlive) | dependency-blocked | not installed |
| Harness long-running task control (cancel/timeout-kill/resource-limits/crash-recovery) | live-proven | M17.8 real cancel+SIGXFSZ+reconcile, orphan-free |
| Harness durable run ledger (transactional state / concurrency / recovery) | staging-ready (multi-process proven) | M17.9 SQLite CAS ledger: one-claimant, terminal-immutable, ownership-safe cancel, exactly-once crash recovery, migration, backup/restore, 11 blocking manifest checks |
| Harness pause/resume/checkpoint | contract_ready | M17.9 capability contract only; process suspension ≠ app checkpointing (deferred) |
| Red-team harness | live | deterministic (M17.9 +19 ledger probes) |
| Backup/restore | deterministic+drill | M13.5 real drill; M17.9 ledger db covered |
| Multi-user isolation | single-user + multi-process tested | cross-user gates + M17.9 spawn concurrency; not multi-user LOAD |
| Harness run monitoring / stuck-run alerting | staging-ready (first slice) | M17.10 deterministic dedup sweep: heartbeat_stale/cancellation_stuck/process_missing, self-resolving, Control Center attention, admin-audited ack, 2 blocking manifest checks |
| Harness alert delivery (durable, retryable, local transport) | staging-ready | M17.11 run_alert_delivery: dedup idem_key, bounded deterministic retry→terminal_failed, restart-safe, concurrency-safe lease claims, credential-free local transport, resolve/ack suppression, opt-in scheduler, 7 blocking manifest checks |
| Production monitoring/alerting (external transports + auto-scheduled) | not built | M17.11 local delivery + opt-in scheduler live; Telegram/email/Slack/cron + incident drill outstanding |
| Multi-harness pipeline (chained live-app workflows) | staging-ready | M17.12 governed SEQUENTIAL fail-closed orchestrator over the sole run_harness_action: additive pipeline_run/pipeline_step ledger tables, one confined workspace, artifact wiring, pre-execution path-escape rejection, honoured approval gates, owner-safe records, Control Center attention, LIVE sqlite→zip chain, 7 blocking manifest checks; parallel DAGs / retry-resume / untrusted spec deferred |
| Workflow intelligence engine | not started | gated on live-execution proof |
| External capability register (ECP P1–P3) + project skills | registered (docs) | SES-000E Part 6; `.grok/skills/*`; MCP inventory; no runtime pilots |
| MCP governance + codebase-memory contract (M18.1) | deterministic-tested | Historical label M17.25 MCP governance (`2223322`); inventory/namespace/write-governance; Continuum BLOCKED_LICENSE |
| Governed codebase memory indexing + hybrid retrieval (M18.2) | deterministic-tested | local SQLite index, provenance, freshness, secret exclusion, CLI/tools, eval set |

## Highest-value NON-blocked evidence gap now
Four live apps (media/database/JSON/archive) now exercise the harness across four
distinct categories, and the archive-security verifier (ZIP-slip/zip-bomb) is
proven live against real hostile archives (M17.7). Remaining safe real-evidence
wins are reliability-oriented (long-running task control, production monitoring)
and are medium/large / less bounded, or are blocked on installs (GUI apps),
permissions (macOS TCC actuation), or credentials (authenticated cloud/browser).
| InsForge provider (read-only pilot) | deterministic-tested | M18.3 allowlisted GET adapter; disabled by default; mock tests |
