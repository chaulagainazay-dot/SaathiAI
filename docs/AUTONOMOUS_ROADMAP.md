# SaathiOS Autonomous Roadmap

## M21–M39 Master Program (2026-07-16)

**Platform program status:** Phase 1 active — **M21.0–M21.4** and **M22 provider migration COMPLETE WITH LIMITATIONS**; not production-certified.
Do not auto-run M21–M39 in one unattended block.

Canonical docs:

| Doc | Role |
|-----|------|
| `docs/M21_39_MASTER_PROGRAM_AUDIT.md` | Intake, conflict map, asset→phase map |
| `docs/M21_39_MASTER_PROGRAM_ROADMAP.md` | Canonical platform M21–M39 roadmap |
| `docs/M21_39_GATE_MATRIX.md` | Per-milestone exit gates + evidence tiers |
| `docs/M21_0_RUNTIME_PRODUCTION_CONFIG.md` | M21.0 architecture + ops |
| `docs/M21_0_VALIDATION.md` | M21.0 validation |

### M21.0 (Runtime Production-Configuration Inventory + Provider Policy) — COMPLETE

Path inventory, production config validator, provider policy + kill switches, gateway kill enforcement, console `prod-config`. Tests: `tests/test_m21_0_production_config.py`.

### M21.1 (Canonical Request Contract + Residual Path Controls) — COMPLETE WITH LIMITATIONS

Extended `InferenceRequest`, `validate_contract`, caller policy registry, residual allowlist, AST bypass guard, gateway enforcement, compat builds contract requests. Legacy chat/llm paths remain allowlisted (not fully migrated). Tests: `tests/test_m21_1_request_contract.py`. Docs: `docs/M21_1_*`. **Not** production certified; live model still env-blocked.

### M21.2 (Provider Availability, Cost, Failover, Circuit Governance) — COMPLETE WITH LIMITATIONS

Canonical provider descriptors, availability/readiness model, Decimal cost policy, failure taxonomy, deterministic retry/failover (defaults off), process-local circuit breaker, kill precedence, cheap_ask proxy blocked, unknown caller test-only. Tests: `tests/test_m21_2_provider_governance.py`. Docs: `docs/M21_2_*`. Live Ollama still env-blocked; production_certified=false.

### M21.3 (Residual Inference Path Migration + Release-Check) — COMPLETE WITH LIMITATIONS

Residual inventory UNKNOWN=0; chat compatibility adapter; `llm.generate` deprecated preflight facade; `_llm_helper` HTTP chain removed; agent/research preflight; transitional unknown FORBIDDEN; `python -m saathi.inference.release_check`. Tests: `tests/test_m21_3_residual_path_migration.py`. Docs: `docs/M21_3_*`. Legacy sinks expire M22/M23; production_certified=false.

### M21.4 (Runtime Consolidation + Production-Configuration Gate) — COMPLETE WITH LIMITATIONS

Canonical `runtime_gate`; release_check integrated into ops release gate; residual manifest validated (count frozen 7 at close); kill-switch matrix; fake/test isolation; certification invariant (`production_certified=false` without live+suite evidence); full suite attempted. Tests: `tests/test_m21_4_runtime_consolidation.py`. Docs: `docs/M21_4_*`. Live Ollama ENVIRONMENT_BLOCKED.

### M22 (Governed Provider Implementation + Legacy SDK Migration) — COMPLETE WITH LIMITATIONS

Provider HTTP/SDK moved under `saathi.inference.adapters` (`http_providers`, `grounding`, `agent_provider`). `llm.generate` pure facade; agent/research facades thin; residual EXPLICIT_LEGACY_EXCEPTION=0; manifest exceptions reduced in M23. Release-check facade purity. Tests: `tests/test_m22_provider_migration.py`. Docs: `docs/M22_*`. Cloud fallback off; production_certified=false.

### M23 — Full governed chat default (COMPLETE WITH LIMITATIONS)

Canonical `saathi.chat.runtime` sole production chat path; ChatRequest + context builder + stream events; chat residual exception removed (manifest exceptions=2 → cloud/openai_compat M24); release/runtime M23 gates. Tests: `tests/test_m23_governed_chat_default.py`. Docs: `docs/M23_*`. production_certified=false.

### M24 — Durable circuit/cost + engine consolidation (COMPLETE WITH LIMITATIONS)

Canonical `DurableGovernanceStore` (SQLite): circuit state, usage ledger, budget reservations, recovery, operator audit. Process-local circuit/cost no longer production authority. Cloud + OpenAI-compat residual exceptions removed (manifest exceptions=0). Tests: `tests/test_m24_durable_provider_governance.py`. Docs: `docs/M24_*`. production_certified=false; live Ollama still ENVIRONMENT_BLOCKED. Do not start M25 without operator authorize.

### M25 — Live local provider certification (BLOCKED — ENVIRONMENT)

Harness `saathi.inference.live_cert_m25` + evidence under `docs/evidence/m25/`. Discovery proves Ollama.app missing (broken symlink), runtime down, no models, memory pressure. No install/start/pull performed. Verdict: `M25 BLOCKED — LIVE LOCAL PROVIDER ENVIRONMENT UNAVAILABLE`. Tests: `tests/test_m25_live_provider_certification.py`. Docs: `docs/M25_*`. production_certified=false. Do not start M26 without operator authorize.

### M26–M28 — Ops + connectors (COMPLETE)

M26 inference ops; M27 governed connector framework; M28 ExecutionGateway connector enforcement. Default connector/inference rollout OFF; production_certified=true (computed package). Do not auto-start next without authorize.

### M29 — Connector identity + trust registry (COMPLETE)

Canonical manifests, trust levels, capability ceilings, registry resolve-only identity, docs CLI. Tests: `tests/test_m29_connector_identity.py`. Docs: `docs/M29_*`. No live SaaS.

### M30 — Connector conformance + certification (COMPLETE WITH LIMITATIONS)

Canonical conformance specification, certification state model, fingerprint/drift/revoke,
credential-free sandbox harness, built-in assessments for `gov.http|mcp|browser|local_tool`.
ACTIVE/CANARY require fresh connector certification (distinct from M25 production cert).
Tests: `tests/test_m30_connector_conformance.py`. Docs: `docs/M30_*`. Evidence: `docs/evidence/m30/`.
Default connector rollout remains OFF. No live SaaS/OAuth. **Do not auto-start M31.**

### Milestone-number namespaces (mandatory)

| Namespace | Meaning |
|-----------|---------|
| **Platform M21–M39** | This monorepo production program (runtime → governed execution → studio → public → cert) |
| **PRODUCT/IELTSAlert M21.x** | Separate product repo `/Users/macbookpro/Saathi/apps/pielts` — **not** platform M21 |
| **M20.10 options A/B/C** | Historical handoff choices; remapped in program roadmap (A→env unlock/M24 evidence; B→M21.0 slice; C→M30/PRODUCT) |

Platform Phase 1 target: **M21** Runtime Consolidation → **M22** Provider migration (done) → **M23** Chat governed default (done) → **M24** Durable governance (done) → **M25** Live cert (BLOCKED env).
Next recommended: operator unlock Ollama **or** **M26** with authorize only. Do not auto-start M26.

Prior series: **M20 COMPLETE WITH LIMITATIONS** (live local inference still environment-blocked).

---

## ECP / MCP memory note (2026-07-15)

External Capability Program **ECP M17.24** completed: SES-000E Part 6 register for
all Priority 1–3 repositories, project Grok skills (GSAP + loop engineering +
audit/health), initial MCP inventory. **No runtime services.**

### Milestone number mapping (MCP governance)

| Historical label | Canonical label |
|------------------|-----------------|
| M17.25 Project MCP Governance and Memory Consolidation | **M18.1** Project MCP Governance and Memory Consolidation |

Originally implemented and committed under the temporary label
“M17.25 — Project MCP Governance and Memory Consolidation” (`2223322`);
canonical roadmap designation is now **M18.1**.

**M18.1 (MCP Governance)** completed: authoritative `docs/MCP_INVENTORY.md`,
canonical `saathi-codebase-memory`, provider-neutral memory contract,
namespace isolation, health/degradation, write governance, Continuum remains
**BLOCKED_LICENSE**.

**M20.5–M20.10 (series plan)** authorized: session ledger/recovery (M20.5) → live small-model cert (M20.6) → orchestrator/inference consolidation (M20.7) → bounded extra callers (M20.8) → integration/security/resource cert (M20.9) → closure + M21 handoff (M20.10). Plan: `docs/M20_SERIES_PLAN_M20_5_TO_M20_10.md`. Master loop: `docs/M20_MASTER_AUTONOMOUS_ENGINEERING_LOOP.md`. **Do not auto-run the whole series in one unattended block.**

**M20.10 (Closure + M21 Handoff)** completed: series closed with limitations; operational runbook + recert path + M21 options; M21 **not** started. Docs: `docs/M20_10_*`.

**M20.9 (Integration / Regression / Security / Operational Certification)** completed with limitations: M20.8 INTENTIONALLY_SKIPPED; authority-boundary + flag + ledger/recovery/approval + TG tests; M20.6 remains environment-BLOCKED; callers stay legacy default; no production claim. Docs: `docs/M20_9_*`, `docs/M20_8_STATUS.md`.

**M20.8 (Bounded Additional Caller Adoption)** **INTENTIONALLY_SKIPPED** at finalization: no live-certified local model (M20.6 BLOCKED); certify M20.3 pair only. Status: `docs/M20_8_STATUS.md`.

**M20.7 (Engineering Orchestrator + Governed Inference Consolidation)** completed: shared read-only `saathi/m20_console` (flags inventory, unified status, CLI discovery, disable procedure); Control Center cells `governed_inference` + `m20_console`; domains remain separate (no second gateway/router/ledger/store merge); defaults still off/legacy; TG unengaged. Docs: `docs/M20_7_*`.

**M20.6 (Live Local Inference Certification)** **BLOCKED** on pilot host: certification suite + 10-case corpus + discovery/selection implemented (`saathi/inference/certification.py`); live run found no usable Ollama binary and zero installed models (no auto-download); defaults remain legacy; TG unengaged. Docs: `docs/M20_6_*`. Unblock: operator-install Ollama + ≤3B model, re-run `python -m saathi.inference.certification run`.

**M20.5 (Canonical Engineering Session Ledger, Integrity Evidence, Recovery)** completed: append-only hash-chained `session_ledger.jsonl`; integrity evidence store; recovery for stale leases / missing PID / resume plans (no auto-launch); CLI `ledger|recover|evidence|resume-plan`. Not a second harness run ledger. Docs: `docs/M20_5_*`.

**M20.3 (Opt-In LLM Caller Migration + Live Small-Model Validation)** completed: inventory of direct `llm.generate` sites; selected exactly two low-risk callers (`cheap_ask`, `prose_clean`); rollout modes `legacy|shadow|governed_local_with_fallback|governed_local_only` (default legacy); compatibility adapter over M20.2 path; shadow metrics; security denials never fall back; chat default unchanged; live Ollama validation harness (honest `unavailable` when no Ollama/model); TG isolated. Docs: `docs/M20_3_*`.

**M20.4 (Engineering Control Center + supervised read-only sessions)** completed: Control Center engineering facet (versioned read model, redacted); repository integrity snapshots + quarantine; bound read-only approvals for real Claude; store locking/leases; CLI control-center/approve-readonly/integrity; mock pilot green; live Claude optional/dry_run if binary missing. Writes/commits/pushes remain disabled. Docs: `docs/M20_4_ENGINEERING_*`.

**M20.2 (Governed Local Inference Execution Path)** completed: ToolIntent/`ModelGateway` path → authoritative ModelRouter → M20.1 runtime → Ollama-first local engine; structured result + evidence events; hardware/concurrency/timeout/host allowlist; default-off (`SAATHI_INFERENCE_ENABLED` + `SAATHI_INFERENCE_GATEWAY_ENABLED`); no global `llm.generate`/chat switch; no OJ process; TG isolated. Docs: `docs/M20_2_GOVERNED_LOCAL_INFERENCE_EXECUTION.md`.

**M20.1 (Selective OpenJarvis Primitive Integration — Slice A)** completed: SaathiOS-native `saathi/inference` (engine contract, registry/discovery, catalogue+provenance, M2 8 GB hardware profile, Ollama/OpenAI-compat/cloud/fake adapters, bounded benchmarks, ModelRouter observation bridge, skill/sandbox gates). OpenJarvis audited as Apache-2.0 **reference only** — no OJ source copied, no OJ process, default-off. ModelRouter remains authoritative; TG unengaged. Not production-ready; normal `llm.generate` path unchanged by default. Docs: `docs/M20_1_OPENJARVIS_*`.

**M20.0 (Governed Engineering Orchestrator)** completed: control/supervision layer for coding-agent engineering work (`saathi/engineering/`). Deterministic backlog + candidate selection, repository readiness, bounded prompt builder, mock + Claude Code adapters, progress monitor, checkpoints, validation coordinator, bounded retry, stop policy, commit/push verifiers, durable handoff, CLI. Disabled by default; reuses Mission Engine / ExecutionGateway / Knowledge Service / run-ledger concepts without duplicating them. Harmless mock pilot + 61 deterministic tests. No merge/deploy/trading. Docs: `docs/M20_0_ENGINEERING_ORCHESTRATOR_*`.

**M19.6.1 (Linux short-video pilot residual)** completed: silent-WAV deterministic narration, assemble video-only fallback, thumbnail seek 0.0 + Pillow fallback; CI Critical Manifest + full suite green on f4065d6.

**M19.6 (CI Critical Manifest Environment Honesty)** completed: fixed Gate-C Critical Manifest failures that misclassified Linux/CI environment limits as security or product regressions (studio quota vs free-disk order, native permission summary schema on non-macOS, multi-app harness/redteam probes requiring ffmpeg when absent). CI installs ffmpeg/jq/sqlite3 for live pilot coverage. Not a product promotion; TG/InsForge untouched.

**M19.5 (Incremental knowledge refresh + change awareness)** completed: commit/fingerprint-aware refresh over M18.2 indexer; git change detection; leases; cache epoch; multi-repo isolation; durable evidence; runtime.refresh() wired. Not production-ready.

**M19.4 (Context Composer + mission context quality)** completed: structured budgeted composer over M19.0 results; profiles coding/repair/audit/architecture/incident; provenance/trust/injection boundaries; mission+repair facades attach `composed` on unified path only; TG/InsForge untouched. Not production-ready.

**M19.3 (Real-Index Knowledge Campaign + controlled promotion)** completed: real registered-index dual-path campaign; durable metrics; promote exactly one caller (`codebase_memory_search`) to `unified_with_fallback` with per-caller/`SAATHI_KS_DISABLE_PROMOTIONS` rollback; TG/InsForge/chat LTM untouched. Not production-ready.

**M19.2 (Shadow Evaluation Campaign + second-wave KS adoption)** completed: campaign metrics, control_center repository facet (opt-in), repair_context_prepare; default legacy; TG/InsForge untouched. Not production-ready.

**M19.1 (Knowledge Service adoption)** first-wave callers via adoption gateway; default rollout `legacy` (M19.3 promotes one pilot caller); shadow/fallback; TG isolated. Not production-ready.

**M19.0 (Unified Knowledge Service)** retrieval router + multi-repo context over M18.2.

**M18.4 (InsForge governed migration write pilot)** structured ops + fingerprint approval + gateway; writes still dual-flag disabled by default.

**M18.3 (InsForge read-only provider pilot)** registers InsForge as data-plane adapter (`saathi/providers/insforge`); elevated by M18.4 for governed migrations only.

**M18.2 (Governed Codebase Memory Indexing & Retrieval)** operationalizes local-first
repository indexing, hybrid retrieval, provenance, freshness, and evaluation.
Continuum pilot only when licence is clarified (do not auto-install).

Browser milestone **M17.25 — Governed Interactive Browser Sessions** remains M17.25
(distinct from the historical MCP-governance temporary label).

Do not auto-start Priority 2/3 installs on the 8 GB Mac.

---
Detected state: branch milestone/m7-security-engine, HEAD 1feb928 (M17.7, four
live apps: FFmpeg/SQLite/jq/zip). Priorities checked this invocation: no open
Critical/High (critical_checks green, red-team 81/81); release blockers are all
environment-blocked (authenticated browser, live approval click, staging
deploy+rollback — need credentials/deploy). Highest ready-now, non-filler gap is
therefore real validation + reliability of an already-built layer.

## Candidate scoring (this invocation)
| candidate | priority | notes | ready-now |
|-----------|----------|-------|-----------|
| **M17.8 long-running harness task control** | #3/#4 | top "actionable without approval" real-debt item; cancel + orphan-free timeout kill + LIVE resource-limit enforcement + durable run journal w/ crash reconciliation; reuses the sole adapter (no second execution engine); no install/permission/credential | **5** |
| production monitoring/alerting | #4 | valuable but medium/large; less bounded for one iteration | 3 |
| AI Studio multi-harness pipeline | #5 | chains live apps; valuable but broader; do after execution reliability is proven | 3 |
| authenticated browser workflow | #5 | needs a safe staging credential (blocked) | 1 |
| native Finder/TextEdit actuation | — | macOS TCC permission required (blocked) | 0 |
| workflow intelligence engine | #6 | large; risks a second execution engine; premature | 1 |
| another system-utility harness | — | explicitly out — would only inflate app count | 0 |

## Decision (this invocation)
Priority chain says: no Critical/High open, release blockers environment-blocked →
take the highest-value ready-now "real validation of an already-built capability"
that also advances "long-session stability / crash recovery". → **M17.8 governed
long-running harness task control**. Bounded, reuses the one adapter boundary, and
is fully live-validatable (real cancel, real SIGXFSZ resource kill, real crash
reconciliation). Turns the top actionable real-debt item from "designed" to
"live-proven".

## M17.9 (this invocation) — durable run ledger, concurrency safety, recovery ops
Start/rollback point: HEAD `2dcfd3d` (M17.8). No higher Critical/High open;
release blockers environment-blocked. Selected the top real-debt item: upgrade
M17.8's single-process JSONL journal into a **transactional SQLite run ledger**.
Delivered: CAS state machine (one-claimant-per-run, terminal immutability, stale-
writer rejection), ownership-safe cancellation, exactly-once idempotent crash
recovery, heartbeats + stuck-run classification, recovery operations, safe
reversible JSONL migration, admin-maintenance CLI (verified OS identity, audited —
NO caller-supplied identity trusted), owner-safe Control Center read model, ledger
db in the backup/restore + integrity gates, and **11 dedicated blocking Critical
Manifest checks**. Multi-PROCESS concurrency proven (spawn, not threads); live
process lifecycle, restart persistence, and backup/isolated-restore proven.
Reuses the ONE adapter (no second execution engine). Verdict: **RUN LEDGER STAGING
READY** — not production-ready (needs multi-user load, production monitoring/
alerting, representative deployment, incident-response drill). Pause/resume/
checkpoint kept `contract_ready` (process suspension ≠ application checkpointing).

## M17.10 (this invocation) — harness run monitoring & stuck-run alerting
Start/rollback point: HEAD `73e97f9` (M17.9). No higher Critical/High open; release
blockers environment-blocked. Selected the bounded first slice of the "production
monitoring" candidate (the roadmap gated it on "a bounded design existing"): a
deterministic, deduplicated, self-resolving stuck-run alerting layer over the M17.9
run ledger. Delivered: ledger `run_alert` store (partial-unique dedup, idempotent
raise, auto-resolve on terminal/reconcile, admin-audited acknowledge), a
`run_monitor.py` sweep (classify → alert → reconcile → self-heal; deterministic,
injectable now/thresholds/is_alive), Control Center attention integration
(`kind: harness_run`), 3 admin-gated CLI commands, and **2 dedicated blocking
Critical Manifest checks**. Multi-PROCESS concurrent-sweep dedup proven; restart
persistence proven. Extends the ledger + Control Center attention + event bus — no
second monitoring stack. Touches no financial/external surface (Trading Guardian
not engaged). Verdict: **HARNESS RUN MONITORING STAGING READY** — not production
(external transports, scheduled sweeps, multi-user load, incident drill remain).

## M17.11 (this invocation) — scheduled monitoring & reliable alert delivery
Start/rollback point: HEAD `28ce958` (M17.10). No higher Critical/High open; release
blockers environment-blocked. Made the M17.10 monitoring substrate operationally
useful: durable, deduplicated, retryable notification DELIVERY over the ledger
(additive `run_alert_delivery` table, unique idem_key, lease-based concurrency-safe
claims, bounded deterministic retry `[0,60,300,900,3600]`s → terminal_failed,
restart-safe, resolve/ack suppression), a narrow transport contract + one
credential-free durable local transport (external providers fail-closed stubs), an
opt-in interval scheduler adapter (default DISABLED, idempotent registration, overlap
lock, mirrors the storage watchdog pattern — no new framework), the full
notification/monitor event taxonomy, Control Center delivery-health + attention
integration, 4 admin-gated CLI commands, and **7 dedicated blocking Critical Manifest
checks**. Multi-PROCESS concurrency proven (dedup/claim/dispatch/stale-reclaim).
Extends the ledger + event bus + Control Center attention + admin gate — no second
monitoring/scheduler/bus/DB/auth. Trading Guardian not engaged (no financial/external
execution; notification stays advisory-compatible). Verdict: **RELIABLE LOCAL ALERT
DELIVERY STAGING READY** — not production (external transports, auto scheduling,
multi-user load, incident drill remain).

## M17.12 (this invocation) — governed multi-harness pipeline
Start/rollback point: HEAD `22c2fe0` (M17.11). No higher Critical/High open; release
blockers environment-blocked. M17.8–M17.11 proved single-run execution + monitoring
+ delivery reliability — clearing the exact gate the roadmap set on the "AI Studio
multi-harness pipeline" candidate ("do after execution reliability is proven"). Made
the four proven live apps (FFmpeg/SQLite/jq/zip) composable into ONE governed,
deterministic, SEQUENTIAL, fail-closed workflow. This is an ORCHESTRATOR, not a
second execution engine: every step runs through the SAME governed
`run_harness_action` (ownership → trust → risk/approval → the sole adapter →
INDEPENDENT verification). Delivered: additive `pipeline_run` + `pipeline_step`
ledger tables (PK-unique, terminal-immutable, owner-safe), a `pipeline.py`
orchestrator (one confined workspace, artifact wiring, fail-closed short-circuit on
the first non-success, pre-execution path-escape rejection, honoured approval gates
— no silent elevation), Control Center pipelines cell + `harness_pipeline`
attention, 3 CLI commands (1 always-on census + 2 admin-gated owner-safe), and **7
dedicated blocking Critical Manifest checks**. LIVE two-application chain proven
(sqlite `safe_mutation` → data.db → zip `pack` → bundle.zip, independently verified,
artifact wired end-to-end). Multi-PROCESS concurrent create dedup proven. Extends
the ledger + event bus + Control Center attention + admin gate — no second execution
engine / trust model / DB / scheduler / bus. Trading Guardian not engaged (approval
gates strengthened, never bypassed). Verdict: **GOVERNED MULTI-HARNESS PIPELINE
STAGING READY** — not production (parallel/branching DAGs, pipeline retry/resume,
untrusted spec ingestion, multi-user load remain).

## M17.13 (this invocation) — autonomous mission engine
Start/rollback point: HEAD `186a72f` (M17.12). No higher Critical/High open; release
blockers environment-blocked. M17.12 proved that real tools compose into ONE governed
workflow; M17.13 adds the layer ABOVE it so the system can be driven by OBJECTIVES,
not tools. HIERARCHY is now Mission → Pipeline → Harness Step → Adapter →
Verification → Ledger. A Mission is ONE business objective (today's IELTS lesson,
daily CEO brief, kitchen inventory audit) carrying strongly-typed validated
parameters, an approval requirement, and a reference to a reusable TEMPLATE — and it
NEVER executes a tool: it DELEGATES to the existing M17.12 `PipelineRunner` (which
delegates to the sole governed `run_harness_action`). Delivered: additive
`mission` + `mission_run` ledger tables (PK-unique, UNIQUE(mission_id,attempt),
explicit fail-closed state machine
draft→(approval_required|approved)→queued→running→{completed|failed|cancelled|blocked}
with immutable terminals, owner-safe field projections, params secret-rejected on
write), a `mission.py` MissionEngine (strong parameter validation BEFORE execution;
owner isolation on every op; approval gates honoured with NO silent elevation;
fail-closed — a mission completes ONLY if its delegated pipeline succeeded, no partial
success; retry rejected unless failed, and a failed retry CLONES a new instance;
trusted-Python templates like the pilots), Control Center missions cell +
`harness_mission` attention (failed → high, approval_required → medium), 6 CLI
commands (1 always-on census + 5 admin-gated owner-safe), and **7 dedicated blocking
Critical Manifest checks**. LIVE proven: a mission completes via a real delegated
governed pipeline (sqlite → data.db → zip → bundle.zip, independently verified); a
pipeline failure fails the mission. Multi-PROCESS concurrent create dedups to exactly
one. Extends the ledger + event bus + Control Center attention + admin gate — no
second execution engine / trust model / DB / scheduler / approval path. Distinct from
the older `saathi/missions/` business-content package (untouched). Trading Guardian
not engaged (approval gates strengthened, never bypassed). Verdict: **AUTONOMOUS
MISSION ENGINE STAGING READY** — not production (untrusted mission-spec ingestion,
live scheduling + event/triggered execution, parallel missions, multi-user load
remain).

## M17.14 (this invocation) — governed mission scheduler & trusted event triggers
Start/rollback point: HEAD `73fd251` (M17.13). No higher Critical/High open; release
blockers environment-blocked. M17.13 delivered objective-driven missions; M17.14 adds
the WHEN layer ABOVE the MissionEngine so approved missions run on a schedule or from
a trusted internal event — without a second scheduler DB, job runner, execution
engine, approval system, or event bus. HIERARCHY: Scheduler/Trusted-Event → Mission
instance → MissionEngine → PipelineRunner → run_harness_action → Adapter →
verification → ledger; the scheduler NEVER executes a tool (static test asserts no
PipelineRunner/adapter/subprocess reference). Delivered: additive `mission_schedule`
+ `mission_occurrence` (UNIQUE dedup_key) + `mission_event_trigger` +
`mission_event_receipt` (UNIQUE dedup_key) ledger tables; deterministic tz-aware due
math (one_time/interval/daily/weekly; DST via zoneinfo; cron omitted); each due time
→ exactly ONE occurrence and each occurrence → at most ONE mission (deterministic
mission id = crash-safe idempotency); lease-based claiming (active lease not
stealable, expired recoverable); restart reconciliation (no duplicate mission);
infra-only bounded retry `[0,60,300,900,3600]`s (NEVER for approval/owner/param/
mission outcome); a trusted event ALLOWLIST with static template binding +
allowlisted scalar payload mapping + durable receipt dedup (payload can't set owner/
template/risk/approval); an opt-in interval runner (default DISABLED); Control Center
scheduler cell + attention; 12 CLI commands (1 always-on census + 11 admin-gated
owner-safe); and **8 dedicated blocking Critical Manifest checks**. LIVE proof: a
scheduled data_bundle mission generated one occurrence, dispatched through the
MissionEngine to a real governed sqlite→zip pipeline (independently verified), re-swept
with no duplicate occurrence/mission, and reconciled after a simulated restart.
Multi-PROCESS + multi-thread concurrent occurrence create each dedup to exactly one.
Extends the ledger + event bus + Control Center attention + admin gate — no second
scheduler/engine/DB/bus. Trading Guardian not engaged (scheduler/event modules carry
no trading surface; scheduling never converts advisory into execution permission).
Verdict: **GOVERNED MISSION SCHEDULING & TRUSTED EVENT TRIGGERS STAGING READY** — not
production (cron, public webhooks, untrusted JSON defs, distributed/parallel
scheduling, production auto-scheduling remain).

## M17.15 (this invocation) — governed pipeline retry, resume & checkpoints
Start/rollback point: HEAD `4cad92a` (M17.14). No higher Critical/High open; release
blockers environment-blocked. Closes the M17.12 deferred gap (pipeline retry/resume/
checkpoint) that M17.14's retry section pointed at. A failed/interrupted pipeline now
CONTINUES FROM ITS LAST INDEPENDENTLY VERIFIED STEP instead of restarting — implemented
inside/around the existing PipelineRunner + ledger, with NO second pipeline/execution
engine, retry framework, verification path, or ledger. Delivered: additive
`pipeline_checkpoint` (UNIQUE per pipeline_id,step_index) + `pipeline_recovery` ledger
tables; a checkpoint written ONLY after a verified success; deterministic fingerprints
(step-definition / dependency / artifact) that reuse ONLY a CONTIGUOUS valid verified
prefix and fail closed on any mismatch (owner, step identity, fingerprints, verify
policy, artifact existence+confinement+integrity, invalidation); category-ALLOWLISTED
bounded retry on the shared RETRY_SCHEDULE (approval/owner/verification/param/tamper/
cancellation/unknown never auto-retry); approval never implied (increased risk
invalidates reuse; resume stops at approval_required; risk-4 manual-only); lease-based
recovery claiming (one winner, active not stealable, expired reclaimable); crash
reconciliation preferring reconcile over duplicate execution (uncertain → stop_uncertain,
never assume success); a governed audited attempt-bounded `reopen_pipeline` (the ONE
exception to pipeline terminal immutability; complete_pipeline unchanged); mission
integration (failed mission pipeline resumes in place, no duplicate mission); Control
Center recovery cell + attention; `pipeline-recovery-health` + 7 admin-gated owner-safe
CLI commands (operator may INVALIDATE but never force-valid); and **9 dedicated blocking
Critical Manifest checks**. LIVE proof: sqlite→zip with an injected transient failure —
step1 verified+checkpointed, step2 transient-fails, retry reuses step1 (not rerun),
step1 revalidated, step2 verified, pipeline succeeds; duplicate resume refused;
tamper of data.db invalidates the checkpoint and reruns from step1. Extends the ledger
+ Control Center attention + admin gate — no second engine. Trading Guardian not engaged
(recovery module has no trading surface; recovery adds no execution path). Verdict:
**GOVERNED PIPELINE RETRY / RESUME / CHECKPOINT STAGING READY** — not production
(parallel/branching DAGs, distributed/remote/cloud checkpoints, untrusted pipeline JSON,
cross-owner reuse, production auto-scheduling remain).

## M17.16 (this invocation) — governed bounded parallel & branching pipeline graphs
Start/rollback point: HEAD `5bc8317` (M17.15). Closes the M17.12/M17.15 deferred gap
(parallel/branching DAG). The pipeline gains a bounded, deterministic, ACYCLIC graph —
one fork, N independent branches, one explicit join barrier (diamond A→(B,C)→D) —
implemented as a thin dependency-aware bounded executor (`pipeline_graph.py`) that
WRAPS the existing PipelineRunner and calls the SAME `_run_step` → `run_harness_action`
for every step. NO second pipeline/execution/DAG engine, scheduler, retry framework,
checkpoint system, approval system, or ledger. Delivered: full pre-exec graph
validation (cycle / unknown-dep / dup-id / self-dep / owner / size / concurrency /
nested-fork / second-join / branch-width / artifact-collision / secret-name /
path-escape / unknown-or-non-executable-harness → no partial exec); bounded
ThreadPoolExecutor (≤4 workers) over a deterministic ready queue; the join barrier via
the dependency mechanism (no partial join); fail-closed on first branch failure (join
never runs, siblings settle honestly, unstarted cancelled, never partial-success);
dependency-CLOSED checkpoint reuse on graph resume (not a linear prefix) reusing the
M17.15 `_validate_checkpoint`; branch-local retry via the shared M17.15 schedule;
durable per-step claims (`pipeline_step_claim`) for exactly-once + crash-safe reclaim;
graph-launch + resume dedup; additive ledger tables (`pipeline_graph`/
`pipeline_dependency`/`pipeline_branch`/`pipeline_step_claim`; the graph IS a
pipeline_run reusing pipeline_step + pipeline_checkpoint); mission integration
(`MissionTemplate.build_graph` launches a graph through the SAME PipelineRunner, no
duplicate mission/occurrence); Control Center owner-safe graph cell + attention; CLI
(`pipeline-graph-health` always + 6 admin-gated owner-safe, resume driven through the
owning mission template — no arbitrary graph JSON, no force-success/skip/bypass); 13
BLOCKING pipeline_graph.* manifest checks; 44 tests. LIVE PROOF: real sqlite→
(sqlite||sqlite)→zip diamond with concurrent verified branches, confinement,
fail-closed, partial reuse, tamper invalidation, dedup, crash-before-join reconcile.
Trading Guardian not engaged (graph layer asserted free of trading surfaces).
Verdict: **GOVERNED BOUNDED PARALLEL/BRANCHING GRAPH STAGING READY** — not production
(cyclic/nested-fork graphs, dynamic mutation, untrusted graph JSON, distributed/remote
execution, cross-owner delegation, production auto-scheduling, live trading remain OUT).

## M17.17 — governed graph mission scheduling & recovery integration (DONE)
Autonomous-loop milestone (start/rollback e7207dd). Joins M17.14 scheduling, M17.15
recovery, M17.16 graph pipelines, and M17.13 MissionEngine so a SCHEDULED occurrence (or
trusted event) launches a GRAPH-backed mission, survives interruption, resumes through the
EXISTING graph + recovery layers, and settles the mission AND occurrence EXACTLY ONCE. No
new execution path: scheduler → MissionEngine → PipelineRunner → bounded graph executor →
run_harness_action → adapter → verification → ledger. Scheduler still delegates ONLY to the
MissionEngine (fresh execution via engine.launch; no direct graph/recovery calls, asserted).
New MissionEngine methods (mission authority): resume_graph_mission / settle_recovered /
reconcile_running_mission + honest graph→mission classification. Honest state map with
approval→approval_required, stop_uncertain→blocked (fail closed), transient failure→deferred
retry_wait→succeeded after recovery. Idempotent + durable (deterministic recovered mission
id; recovery/step/occurrence claims); original failed mission immutable (linked retry). Crash
windows F/G reconciled. Retry = M17.15 allowlist + [0,60,300,900,3600]s. NO new tables (one
read-only helper). Additive default-off scheduler flag. 12 BLOCKING scheduled_graph.*
manifest checks (194 total); 31 deterministic tests; M17.13–16 regression 160 green; full
suite 1844/1 skipped/0 failed. LIVE PROOF (credential-free): scheduled sqlite-root → 2
concurrent verified sqlite branches → zip join; repeat sweep no-dup; injected retryable
branch failure → durable recovery → reuse root+branch_a, rerun branch_b + join once →
mission+occurrence settled once (idempotent); crash F/G reconciled; approval branch blocks
join+schedule without auto-approval. Trading Guardian not engaged (asserted free of trading
surfaces). Verdict: **GOVERNED SCHEDULED GRAPH RECOVERY STAGING READY** — not production
(production auto-scheduling, distributed/multi-region recovery, untrusted graph JSON, dynamic
mutation, public webhooks, live trading remain OUT).

## M17.18 — harness registry boot persistence (DONE)
Autonomous-loop milestone (start/rollback `04be33c` / M17.17). Closes the real-debt
item: `data/application_harnesses/registry.json` was written by `persist()` but never
loaded — in-memory pilot bootstrap only. Delivered: load-on-first-bootstrap
(fail-closed on missing/corrupt/oversized/secret-bearing JSON), persist-on-mutate
(`register`, `import_records`), external records demoted if disk claims executable
trust, pilot code-seed with restrictive-only trust overlay from disk, CLI
`import-cli-anything` now registers+persists, `load_report()` / summary diagnostics,
15 deterministic tests, 5 blocking `registry.*` critical checks. No second registry,
no ledger/schema change, Trading Guardian unengaged. Verdict: **REGISTRY BOOT
PERSISTENCE STAGING READY**.

## M17.18.1 — curated vs runtime memory conventions split (DONE)
Hygiene follow-on after M17.18 (start HEAD after M17.18 + AGENTS.md). Nightly
`memory_reflector` previously appended auto-learned bullets into
`saathi/memory/conventions.md`, leaving durable dirt on every loop. Delivered:
curated baseline stays git-tracked under `saathi/memory/`; runtime learning writes
only to `data/memory/learned_conventions.{md,jsonl}`; agent loads curated then a
short learned slice; `.saathi-agent-state/` + `storage/*.db*` gitignored; 3
deterministic tests. No second memory engine. Verdict: **MEMORY CONVENTIONS SPLIT
STAGING READY**.

## M17.19 — harness registry untrusted persistence hardening (DONE)
Autonomous-loop milestone (start `059671d`). Persisted `registry.json` is treated
as untrusted input: bounded read, versioned envelope (schema_version=1), shared
entry validator for boot/register/import, resource limits, unknown-field reject,
restrictive-only pilot trust overlays, demotion of elevated external trust, atomic
tmp+fsync+replace writes, fail-closed envelope rejection with pilots preserved,
bounded diagnostics (hashes/counts, no full payloads), CLI strict import exit 3,
5 new blocking critical checks, 38 focused tests + M17.18 regression green. No
second registry. Trading Guardian unengaged. Verdict: **REGISTRY UNTRUSTED
PERSISTENCE HARDENING STAGING READY**.

## M17.20 — multi-writer harness registry concurrency (DONE)
Autonomous-loop milestone (start `f0e1a55`). Serializes registry mutations with
process-safe `fcntl.flock` + in-process RLock, durable `revision` CAS,
lock→reload→mutate→atomic-write, `applied_ops` idempotency, bounded lock
timeout, crash-safe prior-file preservation, CLI exit 4/5 for contention/conflict,
5 new blocking critical checks, 33 focused tests. Single-host only (not
multi-host consensus). Trading Guardian unengaged. Verdict: **REGISTRY
MULTI-WRITER CONCURRENCY STAGING READY**.

## M17.21 — Control Center Registry Health cell (DONE)
Autonomous-loop milestone (start `a276843`). Read-only Registry Health object
with deterministic score/status; Control Center cell + overview + attention;
CEO Daily Brief only when unhealthy; safe diagnostics API; 5 blocking critical
checks; 19 focused tests. No second dashboard/registry. Trading Guardian
unengaged. Verdict: **REGISTRY HEALTH CELL STAGING READY**.

## M17.22 — Universal ExecutionGateway Phase 1 (DONE)
Autonomous-loop milestone (start `398d40e`). One authoritative execution
boundary: ToolIntent → validation → permission → risk → approval →
ExecutionGateway.submit → connector/CLI/local/MCP handler → evidence →
security event → run ledger → Control Center + gated CEO brief. Deterministic
states (terminal-immutable), durable ExecutionRecord, digest-bound approval,
idempotency + restart recovery, M17 retry schedule, +5 `execution.*` critical
checks, 25 focused tests. Connector substrate reuses existing approval engine
(no second gateway/queue/approval system). Trading Guardian unchanged. Browser /
n8n / LLM / trading migration deferred. Verdict: **UNIVERSAL EXECUTION GATEWAY
PHASE 1 STAGING READY**.

## M17.23 — Governed Browser Actions through ExecutionGateway (DONE)
Autonomous-loop milestone (start after restored M17.22). Browser actions enter
ExecutionGateway via GovernedBrowser: domain/scheme policy, risk classification,
digest-bound approval, idempotency, uncertain-outcome non-retry, prompt-injection
isolation, workspace downloads/uploads, CC browser cell + gated CEO brief.
Reuses BrowserService tiers (no second engine). 46 focused tests; +6 browser.*
checks. Residual: default BrowserService.open ungoverned for compat; live
interactive CDP paths deferred. Trading Guardian unengaged. Verdict:
**GOVERNED BROWSER ACTIONS STAGING READY**.

## M17.24 — Eliminate Residual Ungoverned Browser Dispatch Paths (DONE)
Autonomous-loop milestone (start `f2f262f`). Inventory of all browser dispatch
paths; production singleton `BrowserService(allow_direct=False)` defaults to
gateway; raw agent-browser / AppleScript / ChatGPT browser fail closed (optional
`SAATHI_ALLOW_RAW_BROWSER`); BrowserConnector production path governed; human
`/api/v1/human/test` requires governed intent + approval/env; AST import/launch
allowlist in `saathi/browser/guard.py`; context attribution (actor, mission/run,
approval, schedule, trigger, retry, checkpoint, mission forgery, trading
isolation); +5 blocking `browser.*` critical checks; 30 focused M17.24 tests.
Trading Guardian unengaged for ordinary browse; trading-classified actions deny
without TG auth. No live trading, no deploy, no push. Verdict:
**ALL PRODUCTION BROWSER DISPATCH PATHS GOVERNED**.

## M17.25 — Governed Interactive Browser Sessions, Actions, and Human Handoffs (DONE)
Autonomous-loop milestone (start `caca1da` / tag `m17.24-browser-governance-complete`).
Extends M17.24 from navigation/dispatch into interactive execution:
`InteractiveBrowser` + `BrowserSessionStore` (ownership, leases, lifecycle,
action ledger, handoffs, checkpoints); action taxonomy (read_only → financial);
target resolution (ambiguous/missing/coordinates blocked); commit boundary
(submit requires dedicated approval + idempotency + pre-commit checkpoint —
navigation approval insufficient); human handoff workflow (pause, claim,
complete/decline, validated resume); production hard-blocks
`SAATHI_ALLOW_RAW_BROWSER`; agent click/fill/type route through interactive
sessions; +5 blocking critical checks; 34 focused tests. Trading Guardian
isolation preserved. No live external side effects, no push/deploy. Verdict:
**INTERACTIVE BROWSER SESSIONS, ACTIONS, AND HUMAN HANDOFFS GOVERNED**.

## M17.26 — Production Browser Adapter, Domain Policy, Evidence Redaction, Workflow Migration (DONE)
Autonomous-loop milestone (start `7b21915` / M17.25). Connects governed sessions
to real adapter boundary: `ProductionBrowserAdapter` (sandbox/CDP) +
`HumanMacAdapter` under `adapter_contract` (attach/validate/health/act/reconcile);
environment-specific `DomainPolicyService` (production deny-by-default, HTTPS,
no localhost/private/file/javascript, deceptive-domain normalization, redirect/
popup revalidation); `EvidenceRedactionPipeline` (classification, deterministic
masks, suppress secrets, OCR optional-only); workflow step schema +
`execute_workflow_step` → `InteractiveBrowser.act`; adapter health/reconnect/
kill-switch; Control Center privacy-safe snapshot; +5 blocking critical checks;
90+ focused M17.26 tests. Trading Guardian isolation preserved; no live trading,
no real external browser actions, no push/deploy. Verdict:
**PRODUCTION BROWSER ADAPTERS, DOMAIN POLICY, WORKFLOW MIGRATION, AND EVIDENCE REDACTION GOVERNED**.

## Blocked / deferred (need user action or larger scope)
- authenticated browser / cloud connector workflow — needs a safe staging account.
- native Finder/TextEdit actuation — macOS Accessibility (TCC) not granted.
- GUI harness apps (LibreOffice/Blender/Kdenlive) — not installed.
- staging deploy + live rollback drill — needs a deploy target (no push/deploy).
- pause/resume/checkpoint, workflow intelligence, production monitoring — larger,
  next candidates once a deploy/credential path or a bounded design exists.

## PRODUCT/IELTSAlert track (not platform M21)

IELTSAlert revenue work lives in **`/Users/macbookpro/Saathi/apps/pielts`** under **product** milestone labels (`docs/M21_*` in that repo).
In SaathiAI docs, refer to it as **PRODUCT/IELTSAlert M21.x** so it never collides with **platform M21** (Runtime Consolidation). Not a SaathiOS platform rewrite.

## M32 — Governed Provider-Adapter Pilot, End-to-End Connector Validation, Shadow Operations (DONE)
Autonomous-loop milestone (start `206795f` / M31 credentials complete). Adds one
bounded, governed provider-adapter pilot proving the full path: intent → manifest/
registry → connector certification → provider config → account/credential readiness
→ policy → approval → ExecutionGateway → connector runtime → provider adapter →
normalized result → redaction → evidence → incident/health — WITHOUT bypassing any
M27–M31 control. New `saathi/connectors/providers/`: canonical `ProviderAdapter`
contract; provider identity registry (canonical alias resolution, fail-closed
prohibition of financial/trading/social-write providers); secret-free config with
endpoint/side-effect/data-class policy; request/response normalization (injection
rejection, sensitive-data stripping, raw-response containment); canonical error
taxonomy; deterministic bounded retry; fingerprint-bound idempotency; bounded
rate-limit awareness; provider health + quarantine (distinct from connector/account/
credential); provider verification fingerprint + drift + NON-mutating eligibility
read (M31 correction preserved); composed execution eligibility (M25+M30+M32+M31+
rollout+approval); leak-scanned evidence; CLI; `EchoProviderAdapter` pilot over a
deterministic in-process `provider_simulator` (loopback only). Pilot: `saathi.echo.v1`
on `gov.http`, READ_ONLY, credential-free, OFF/SHADOW only. Highest verification =
`SIMULATION_VERIFIED`. 128 focused tests; M27–M31 regression green; gov connector
certs re-assessed fresh after allowlisting the provider runtime. No CANARY/ACTIVE,
no real credentials/accounts/writes, no financial/trading provider. Trading Guardian
UNCHANGED / UNENGAGED. Verdict: **GOVERNED PROVIDER-ADAPTER PILOT — SIMULATION-VERIFIED**.

## M36 — Operator-Controlled Real Sandbox Credential Verification (2026-07-18)

**Status:** Implementation complete offline; real sandbox session **not exercised** (no disposable credential reference supplied).

- Composition of M31–M35 + M33/M34 transport
- Identity: `GET /user`; operation: `GET /meta` on `github_meta`
- Call budget 3; rollout remains OFF; M37 not started
- Evidence: `docs/evidence/m36/`
- Module: `saathi/credentials/m36.py`

## M37 — Real Sandbox Verification, Provider Generalization, Security Certification (2026-07-18)

**Status:** `SECURITY_CERTIFIED_WITH_LIMITATIONS` (live sandbox not exercised).

- Provider contract: identity/health/operation/capabilities/qualification/cleanup
- Reference provider: github_meta only
- Negative matrix: 13/13 offline
- Evidence: docs/evidence/m37/
- Modules: saathi/credentials/sandbox_provider.py, saathi/credentials/m37.py
- M38 not started

## M38 — Multi-Session Reliability, Recovery, Canary Readiness Evaluation (2026-07-18)

**Status:** READY_WITH_LIMITATIONS (live multi-session not exercised; CANARY not granted).

- MultiSessionCoordinator with explicit state machine
- Bounded concurrency, aggregate budgets, deterministic retry
- Recovery/reconcile without secret reopen from evidence
- Canary readiness evaluator (read-only)
- Evidence: docs/evidence/m38/
- Module: saathi/credentials/m38.py
- M39 authorized for implementation after M38 tip

## M39 — Live Disposable Sandbox Validation & Canary Authorization Decision (2026-07-18)

**Status:** M39 IMPLEMENTATION COMPLETE — OFFLINE CERTIFIED, LIVE VALIDATION BLOCKED (operator disposable secret reference required; CANARY not granted).

- Live preflight fail-closed; feature flag `SAATHI_M39_ALLOW_LIVE_SANDBOX_VALIDATION`
- Secret reference only (Keychain / env name / approved store); 10 runtime acks
- Live single + multi-session runners composed from M36–M38 (github_meta GET /user + /meta only)
- Canary eligibility evaluator (read-only; never grants CANARY)
- Evidence: docs/evidence/m39/ (live statuses NOT_EXERCISED)
- Module: saathi/credentials/m39.py

**Explicit live-dependent state (offline checkpoint):**
- live single-session: NOT_EXERCISED
- live multi-session: NOT_EXERCISED
- external credential revocation: NOT_EXERCISED
- live encrypted-store wiring: NOT_EXERCISED
- CANARY: NOT GRANTED
- ACTIVE: NOT GRANTED
- M40 production authorization: NOT GRANTED
- M40 not started

## M39.1 — Operator Live-Validation Dry-Run Tooling (2026-07-19)

**Status:** OFFLINE OPERATOR TOOLING COMPLETE (PRE-M40 offline readiness extension).

- Module `saathi/credentials/m39_1.py` composes M39; introduces no new subsystem
- CLI: `m39-1-plan`, `m39-1-preview`, `m39-1-backend-availability`,
  `m39-1-revocation-checklist`, `m39-1-diagnostics`, `m39-1-emit-evidence`
- Dry-run execution plan, command preview, secret-backend availability (no `get()`),
  revocation checklist, redacted diagnostics — all offline, no secret resolution
- Tests: 25 passed; evidence `docs/evidence/m39_1/` (deterministic, leak-clean)
- Authorities unchanged: CANARY / ACTIVE / M40 production authorization NOT GRANTED
- Plan: `docs/PRE_M40_OFFLINE_READINESS_PLAN.md`; next: M39.2
