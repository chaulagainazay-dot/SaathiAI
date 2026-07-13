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

## Blocked / deferred (need user action or larger scope)
- authenticated browser / cloud connector workflow — needs a safe staging account.
- native Finder/TextEdit actuation — macOS Accessibility (TCC) not granted.
- GUI harness apps (LibreOffice/Blender/Kdenlive) — not installed.
- staging deploy + live rollback drill — needs a deploy target (no push/deploy).
- pause/resume/checkpoint, workflow intelligence, production monitoring — larger,
  next candidates once a deploy/credential path or a bounded design exists.
