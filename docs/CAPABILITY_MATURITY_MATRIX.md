# SaathiOS Capability Maturity Matrix (as of M72 implementation e39b1bb)

Levels: implemented < deterministic-tested < security/red-team-tested < live-tested < production.

| capability | maturity | evidence |
|-----------|----------|----------|
| Autonomous Mission Runtime (M69–M72) | deterministic+live-browser-tested | Durable hierarchy/DAG/budgets/checkpoints/evidence/reviews; bounded role orchestration via PlatformAgentRuntime→ExecutionGateway; authenticated dashboard; atomic final certification; 18 focused, 138 related, full 5,257 passed/1 skipped; production browser 33+3+2 PASS; single-host, not production |
| Live local provider certification (M25) | environment-blocked | harness+evidence; Ollama broken symlink/app missing; no models; production_certified=false; never mock-as-live |
| Durable provider governance (M24) | deterministic-tested | SQLite circuit/cost/reservation; multi-process budget; residual exceptions=0; release/runtime M24 gates; production_certified=false |
| Governed residual inference paths + release-check (M21.3) | deterministic-tested | residual inventory UNKNOWN=0; release_check pass; chat adapter; unknown caller fail-closed; live cert blocked |
| Runtime consolidation + production-configuration gate (M21.4) | deterministic-tested | runtime_gate; release integrated; cert invariant false; kill matrix; live Ollama env-blocked |
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
| InsForge governed migration write pilot | deterministic-tested | M18.4 plan/preflight/approval/idempotency/verify; no raw SQL |
| Unified Knowledge Service + retrieval router | deterministic-tested | M19.0 multi-source plan/rank/dedupe/context; M18.2 compat |
| KS adoption + shadow campaign (M19.1/19.2) | deterministic-tested | first+second wave; default legacy; campaign metrics; not prod |
| Real-index campaign + pilot promotion (M19.3) | deterministic-tested | real CBM index eval; codebase_memory_search → unified_with_fallback; not prod |
| Mission context composer (M19.4) | deterministic-tested | structured sections/budgets/trust/injection; not prod |
| Incremental knowledge refresh (M19.5) | deterministic-tested | commit/fingerprint refresh, leases, cache epoch; not prod |
| CI Critical Manifest honesty (M19.6) | deterministic-tested | quota mock, native summary schema, env-honest multi-app probes; CI host tools |
| Unified inference runtime + model catalogue (M20.1 OJ Slice A) | deterministic-tested | `saathi/inference` engines/registry/catalogue/hardware/bench/router_bridge; default-off; ModelRouter authoritative; OJ concepts only; TG isolation tests |
| Governed local inference gateway path (M20.2) | deterministic-tested | ExecutionGateway/ModelGateway → ModelRouter → Ollama engine; structured result; hardware/concurrency gates; dual flags default-off; no global llm switch; TG isolation |
| Engineering Control Center + read-only agent pilot (M20.4) | deterministic-tested | CC facet + integrity quarantine + bound approvals + store locks; mock supervised session; Claude dry_run if absent; writes/commits/pushes off; TG isolation |
| Governed Engineering Orchestrator (M20.0) | deterministic-tested | `saathi/engineering` control plane; selector/readiness/prompt/adapter/monitor/validation/retry/stop/commit-push/handoff; mock pilot; disabled-by-default; 61 tests; TG isolation; not production |
| Opt-in governed local LLM caller adoption (M20.3) | deterministic-tested | ≤2 callers (`cheap_ask`,`prose_clean`); rollout legacy/shadow/governed±fallback; compat adapter; live harness honest-unavailable; 34+ tests; chat default unchanged; not production |
| Engineering session ledger + integrity evidence + recovery (M20.5) | deterministic-tested | append-only hash chain; evidence baselines/violations; lease/PID recovery; resume plan no auto-launch; not harness run_ledger; not production |
| Live local model certification suite (M20.6) | deterministic-tested; live **environment-blocked** | cert corpus+runner; no download; live BLOCKED without installed ≤3B model; injected quality path tested; callers stay legacy |
| M20 console consolidation (orchestrator + inference) | deterministic-tested | `saathi/m20_console` flags/status/CLI; CC facets; domain isolation asserted; no execution; not production |
| M20 final certification (M20.9) | deterministic-tested; live model **blocked** | authority/flags/ledger/approval/TG suite; M20.8 skipped; not production |
| M20 series closed (M20.10) | documented pilot close | runbook + M21 handoff; not production; live inference still env-blocked |
| M21–M39 master program init | documented (SOURCE_INSPECTED) | `docs/M21_39_MASTER_PROGRAM_*` + gate matrix; not production |
| M21.0 runtime prod-config + provider policy | deterministic-tested | path inventory; prod_config validator; provider kill switches; gateway kill; `tests/test_m21_0_*`; not production; not full M21 |
| M21.1 canonical request contract + residual controls | deterministic-tested | `validate_contract`; caller_policy; residual_paths; bypass_guard AST; gateway enforcement; legacy chat allowlisted; `tests/test_m21_1_*`; not production |
| M21.2 provider availability / cost / failover / circuit | deterministic-tested | descriptors; availability; Decimal cost; failure taxonomy; circuit (durable as of M24); cheap_ask proxy blocked; `tests/test_m21_2_*`; live Ollama blocked; not production |
| M24 durable circuit/cost + engine consolidation | deterministic-tested | `governance_store`/`governance_service`; reservation protocol; recovery; cloud+openai_compat CANONICAL; `tests/test_m24_*`; residual exceptions=0 |
| PRODUCT/IELTSAlert revenue (pielts M21.x) | product-repo pilot (out of band) | Separate repo `/Users/macbookpro/Saathi/apps/pielts`; **not** platform M21 |
