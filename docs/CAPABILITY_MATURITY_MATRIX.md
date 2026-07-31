# SaathiOS Capability Maturity Matrix (as of M311 certification)

| Read-only market observation (M304–M311) | deterministic-tested; browser-certified-with-limitations; **validation not trading; offline fixtures; no broker login/oauth/credentials/orders/accounts** | `saathi/platform/tg/market_observation/`; snapshots+quotes+history+metadata+exchange status+CA+benchmarks; `/trading/market-observation`; `cert:m311`; live trading not authorized |
| Institutional portfolio & risk intelligence (M296–M303) | deterministic-tested; browser-certified-with-limitations; **paper/research only; not regulatory capital; not investment advice** | `saathi/platform/tg/portfolio_risk/`; analytics+limits+optimiser V2+scenarios+committee V2; `/trading/portfolio-risk`; `cert:m303`; live/connectivity not authorized |
| Institutional paper trading simulation (M288–M295) | deterministic-tested; browser-certified-with-limitations; **virtual exchange only; no broker; no real order routing** | `saathi/platform/tg/paper_simulation/`; matching+book+ledger+kill switch; `/trading/paper-simulation`; `cert:m295`; live/connectivity not authorized |
| Autonomous research orchestrator (M280–M287) | deterministic-tested; browser-certified-with-limitations; **research-only; in-process workers; no broker/orders** | `saathi/platform/tg/research_orchestrator/`; queue+scheduler+budget+templates+notebook+hypotheses; `/trading/research-orchestrator`; `cert:m287`; composes M248/M256/M272; live/connectivity not authorized |
| Multi-strategy research lab, portfolio optimisation & adaptive regime intelligence (M272–M279) | deterministic-tested; browser-certified-with-limitations; **research-only; offline-first; pre-registration required; paper candidate ≠ execution** | `saathi/platform/tg/research_lab/`; experiment registry+fair comparison+robustness+regimes+portfolio+ensembles+stress+candidate gates; `/trading/research-lab`; `cert:m279` WITH_LIMITATIONS; preserves AAPL/BTC OOS failures; human review required; live/connectivity/canary/orders not authorized |
| Intelligence recovery, clean-clone reproducibility & bounded historical data (M264–M271) | deterministic-tested; browser-certified-with-limitations; **M248–M255 committed; clean-clone certified; bounded real historical OHLCV qualified with limitations** | recovered `saathi/platform/tg/intelligence/` into Git; dual surfaces with market_data; clean clone 37+10+build+m255+m263; AAPL+BTCUSDT frozen checksummed snapshots (raw gitignored); OOS validation honest-fail; `cert:m271`; historical status BOUNDED_REAL_HISTORICAL_DATA_VALIDATED_WITH_LIMITATIONS; live/connectivity/canary/orders not authorized |
| Market data foundation, dataset governance & research-grade signal validation (M256–M263) | deterministic-tested; browser-certified-with-limitations; **research-only; offline-first; registered datasets required; no broker; no credentials; no orders** | `saathi/platform/tg/market_data/`; registry+licence+provenance+ingestion+quality+CA+bias+features+signal validation; `/trading/research-data`; `cert:m263` WITH_LIMITATIONS; 23 focused + 37 II+MD + 10 FE unit; SYNTHETIC_TEST_DATA labelled; extended by M264–M271 historical qualification; live/connectivity/canary/orders not authorized |
| Institutional investment intelligence & portfolio brain (M248–M255) | deterministic-tested; browser-certified-with-limitations; **paper intelligence only; now committed via M264 recovery** | `saathi/platform/tg/intelligence/`; strategy registry, portfolio, backtest v2, walk-forward, Monte Carlo, explainable AI, committee, command center; `/trading/intelligence`; `cert:m255` WITH_LIMITATIONS; live/connectivity not authorized |
| Provider selection, RO canary design & human authorization package (M240–M247) | deterministic-tested; browser-certified-with-limitations; **planning-only; no real connectivity; no credentials; canary not authorized** | `saathi/platform/tg/provider_canary_planning/`; preferred Alpaca (recommendation only); fallback Kraken; eligibility ELIGIBILITY_UNCONFIRMED; capability map provider_adapter_implemented=false; ceremony DOCUMENTED_NOT_EXECUTED; owner package APPROVE_PLANNING_PACKAGE_ONLY only; transport REAL_PROVIDER_TRANSPORT_FORBIDDEN; `/trading/provider-canary-planning`; `cert:m247` WITH_LIMITATIONS; 23 focused + 79 M216–M247 + 15 FE unit; live/connectivity/canary not authorized |

Levels: implemented < deterministic-tested < security/red-team-tested < live-tested < production.

| capability | maturity | evidence |
|-----------|----------|----------|
| Read-only broker readiness & credential lifecycle simulation (M224–M231) | deterministic-tested; browser-certified-with-limitations; **simulation-only; no real connection; no real credentials** | `saathi/platform/tg/broker_readiness/`; adapter contract SIMULATED_NOT_CONNECTED; policy engine deny write/real; lifecycle refs only; scope least-privilege; transport guard REAL_PROVIDER_TRANSPORT_FORBIDDEN; snapshots+recon recommendations only; M230 fail-closed drills; `/trading/broker-readiness`; `cert:m231` PASS_WITH_LIMITATIONS; 21 focused + 154 TG M166–M231 + 246 FE; production/live/read-only-prod not authorized |
| Clean-clone reproducibility, supply-chain assurance & RO authorization planning (M232–M239) | deterministic-tested; browser-certified-with-limitations; **planning-only; no real connectivity; no credentials** | `saathi/platform/tg/integration_assurance/`; source audit ALL_REQUIRED_SOURCE_COMMITTED; clean-clone WITH_LIMITATIONS; env preflight fail-closed; dep inventory+lock gates; CycloneDX SBOM unsigned; provenance; threat model+gates; auth max READ_ONLY_CANARY_PLANNING_ELIGIBLE with real_connectivity=false; owner sign-off automation forbidden; `/trading/integration-assurance`; `cert:m239`; 17 focused + 39 M216–M231 + 246 FE; live/connectivity not authorized |
| Broker sandbox architecture & trust framework (M216–M223) | deterministic-tested; browser-certified-with-limitations; **sandbox-only; no live broker** | `saathi/platform/tg/broker_sandbox/`; catalog brokers NOT_CONNECTED; metadata credential refs; in-process emulator only; trust pipeline sandbox-scoped; `/trading/broker-sandbox`; `cert:m223` |
| Operational Graduation / multi-campaign paper ops (M208–M215) | deterministic-tested; browser-certified-with-limitations; **paper-only; no live authority** | `saathi/platform/tg/paper_activation/ops/` over durable paper gov; multi-campaign manager; health classes; graduation never live; recommend-only intelligence; rolling analytics; 12-scenario ops sim; immutable campaign cert; `/trading/ops-graduation`; `cert:m215` PASS_WITH_LIMITATIONS; 15 focused + 115 TG + 5568 backend + 240 FE; production/live not authorized |
| Durable multi-process paper ledger (M200–M207) | deterministic-tested; browser-certified-with-limitations; **paper-only** | SQLite WAL paper_gov; event ledger; long-horizon campaigns; recovery; no live |
| Paper activation governance (M192–M199) | deterministic-tested; browser-certified; **paper-only** | Owner-approved PAPER_ELIGIBLE→PAPER_ACTIVE; portfolio cash sim; risk halt; kill switch; no exchange |
| Live Conversational Intelligence (M80–M86) | deterministic+live-local-model-tested; synthetic-browser-media | Central ConversationService; Ollama qwen2.5:1.5b NDJSON stream; multi-turn memory; barge-in cancel+late-chunk reject; intent propose-only; Voice Runtime wired; templates removed from default path; M85 synthetic getUserMedia PASS; production not authorized |
| Knowledge and Grounding Runtime (M87–M94) | deterministic-tested; browser-cert-API+panel | Platform `saathi.platform.knowledge` lexical index + incremental ingest; authority/freshness/tenancy; ConversationService grounding + citations; injection data-only; `/knowledge/grounding` UI; production not authorized |
| Agent Orchestration Runtime (M95–M102) | deterministic-tested; browser-cert | `saathi.platform.orchestration` objective intake/plan compile/validate; 12 policy roles; Mission Runtime execution only; bounded retries; `/orchestration` workspace; production not authorized |
| Distributed Worker Fleet Runtime (M103–M111) | deterministic-tested; browser-cert Phase A | Extends M56 ClusterCoordinator; admission/fencing/leases/reconciliation/recovery; loopback multi-worker; PlatformAgentRuntime→ExecutionGateway only; `/fleet` workspace; LAN/cloud/production not authorized |
| Skill Ecosystem Runtime (M112–M120) | deterministic-tested; browser-cert | `saathi.platform.skills` manifest/validation/lifecycle/upgrade/rollback; local packages only; ToolRegistry+ModuleRegistry extended not replaced; ExecutionGateway sole tool path; `/skill-runtime`; marketplace/production not authorized |
| Universal Application Runtime (M121–M129) | deterministic-tested; browser-cert | `saathi.platform.apps` AppRuntime lifecycle/workspace/backup/restore; multi local business apps; ModuleRegistry extended; no gateway bypass; `/apps` launcher; marketplace/production not authorized |
| Real-Time Voice Runtime (M79) | deterministic-tested; browser-path code-complete | Central VoiceSessionManager + input/VAD/STT/conversation/SpeechRuntime/playback; barge-in; RBAC voice.listen/transcribe/session.read; platform APIs; shell Live Voice dock; 17 backend + 10 frontend; M74 regression 15; no auto Whisper; production not authorized |
| Provider-neutral Voice Output Foundation (M73–M78) | deterministic+native-runtime-tested; browser-certified (M78) | Central persisted SpeechService, bounded lifecycle/queue/cancel/recovery, authenticated scoped API, evidence/audit, shell and IELTS controls; M78 browser re-cert PASS for explicit Play path |
| macOS system speech provider | native-runtime-tested (English backend) | `/usr/bin/say` AIFF: cold 4.539s, warm 1.663s, ~48.3MB max RSS, cancel 46.04ms; authenticated range API; no network; production/browser playback not certified |
| VoxCPM optional speech adapter | implemented; configured-not-installed | Explicit disabled GGUF/Metal or loopback-service modes; no import/start/download; model paths required; no package/model present; inference/quality/languages not verified or certified |
| Voice cloning | capability-disabled | Profile/reference validation rejects enrollment and active consent; providers report cloning false; no clone API; future consent/rights/labeling/revocation/deletion controls required |
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

## Connectivity Governance (M312–M319)

| Capability | Maturity | Notes |
|------------|----------|-------|
| Connectivity charter | GOVERNANCE_ONLY | v1.0.0 finalized |
| Authority lattice | GOVERNANCE_ONLY | no implicit expand |
| Provider registry | GOVERNANCE_ONLY | docs/mock only, not connected |
| Approval framework | GOVERNANCE_ONLY | APPROVED_NOT_ACTIVE max |
| Credential policy | GOVERNANCE_ONLY | synthetic refs only |
| Emergency shutdown | GOVERNANCE_ONLY | dominates authority |
| Threat model | GOVERNANCE_ONLY | 68 threats catalogued |
| Provider connection | PROHIBITED | not started |
| Live trading | PROHIBITED | not authorized |

## Credentialless Provider Contracts (M320–M327)

| Capability | Maturity | Notes |
|------------|----------|-------|
| Provider contract charter | MOCK_CONNECTIVITY_ONLY | offline and credentialless |
| Provider-neutral interfaces | MOCK_CONNECTIVITY_ONLY | contracts grant no authority |
| Quotes | SUPPORTED_OFFLINE | deterministic synthetic fixtures |
| Candles | SUPPORTED_OFFLINE | deterministic synthetic fixtures |
| Trades | SUPPORTED_OFFLINE | deterministic paginated fixtures |
| Order books | SUPPORTED_OFFLINE | deterministic synthetic fixtures |
| Symbols | SUPPORTED_OFFLINE | deterministic paginated fixtures |
| Market status | SUPPORTED_OFFLINE | fixed synthetic venue state |
| Replay transport | MOCK_CONNECTIVITY_ONLY | integrity-checked fixtures |
| HTTP / WebSocket / socket transport | PROHIBITED | absent and isolated |
| Provider SDKs | PROHIBITED | absent; no dynamic imports |
| Balances | FORBIDDEN_BY_GOVERNANCE | no implementation |
| Positions | FORBIDDEN_BY_GOVERNANCE | no implementation |
| Orders | FORBIDDEN_BY_GOVERNANCE | no implementation or execution |
| Transfers / withdrawals | FORBIDDEN_BY_GOVERNANCE | no implementation |
| Real provider connection | PROHIBITED | not started |
