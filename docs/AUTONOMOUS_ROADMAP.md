# SaathiOS Autonomous Roadmap

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
