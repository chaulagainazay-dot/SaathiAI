# SaathiOS — Business

## Reliability goals (Auto-Repair Loop)

SaathiOS is a daily-use operating system; silent breakage erodes trust faster
than missing features. The Auto-Repair Loop exists to keep the platform
dependable without a human babysitting every failure.

- **Reduced downtime** — recoverable failures (import collisions, unawaited
  coroutines, event-bus regressions, broken routes) are detected, repaired, and
  verified automatically, shrinking mean-time-to-recovery from hours to minutes.
- **Repair auditability** — every repair produces an incident record (category,
  root cause, files changed, tests before/after, repair commit, rollback commit,
  status, confidence) in `data/repair_history.json`, and a local git commit with
  a structured message. Nothing is changed without a trail.
- **Customer trust** — the system never claims success without evidence. A user
  is told plainly when a task was not executed or a connector is not connected,
  instead of receiving a confident but false completion.
- **Human-approval boundaries** — money, credentials, deployments, migrations,
  permission changes, and dependency upgrades always stop for explicit human
  approval. The loop can make the platform self-healing for mechanical faults
  without ever taking an irreversible or costly action on its own.

## Cost-control rules

- No paid external services are introduced by the repair system; it reuses the
  repo's local + open-source components (git, pytest, the existing event bus,
  health checks).
- Bounded work per incident: `max_attempts_per_incident=2`,
  `max_files_per_auto_repair=8`, `max_patch_lines=400`, configurable runtime
  cap. Repeated failures escalate to a human rather than burning cycles.
- Diagnose-only is the default; code changes require a vetted strategy and a
  passing verification ladder, so compute is spent only on repairs likely to
  land.

## What it does NOT do

No autonomous push/deploy, no credential rotation, no email send/delete, no
trades or transfers, no database deletion, no security-control changes. These
remain human decisions by design.

## Dream progress semantics (Repair 3)

The CEO dashboard's dream progress (`dreamPct`) is a **percentage of the
7,938,838.98 USD dream target** — 1.0 means 1% earned. One canonical
calculation (`dream_progress_pct`) feeds every surface, so the Home screen,
briefing, and reports can never disagree. With no recorded revenue the
dashboard shows 0 — real zeros, never fabricated progress. The CEO Home
always presents exactly three real next-actions with Finance review ranked
first — the standing daily discipline.

## Saathi Chat (M8)

One conversation surface now fronts the whole platform: missions, knowledge,
projects and agents flow into every reply automatically, and every model call
is gateway-audited with a visible execution trail. Business value: decisions
made in chat are traceable (who/what/cost/duration), conversations are never
lost (durable store + checkpoints), and failed inference is reported honestly
instead of masked with fabricated answers — the same no-fake-completions
standard as the repair system.

## Unified Memory (M9)

SaathiOS now remembers across conversations, projects, and the business itself
— preferences, decisions, rules, and architecture surface automatically in
chat, each traceable to its source. Value: continuity (the platform stops
re-asking what it already knows), auditability (every retrieval logged with
why-it-matched), and trust (deleted memory truly disappears from results;
nothing is fabricated). Privacy is enforced by scope firewalls — user, project,
and agent memories never leak across boundaries.

## Multi-Agent Runtime (M10)

Complex work (build, research, architecture, business analysis) now runs as a
bounded team of specialist agents — planned, delegated, verified, and
independently reviewed — with every step auditable and every high-impact action
gated behind the owner's explicit approval. Value: more capability without loss
of control. Agents cannot self-approve, cannot bypass the ExecutionGateway, and
cannot widen their own permissions; money, deploys, and external sends stay
manual. Runs are resumable and never silently exceed their budget.

## Voice OS (M12)

Ajay can now talk to SaathiOS instead of typing — the same Chat brain,
memory, and multi-agent runtime, just spoken. Value: hands-free operation
while driving/cooking/multitasking, faster capture of business decisions in
the moment they're made, and voice approvals for agent actions that still go
through the exact same ownership and expiry checks as clicking Approve in the
UI — speed without weakening the safety model. Privacy-first by default: no
recording is ever kept unless explicitly turned on.

## AI Studio (M13)

SaathiOS can now take a content objective and drive it through research,
script, storyboard, media, assembly, thumbnail, SEO, and review — producing
real, verifiable media locally (images, narrated video, thumbnails) with every
step costed and auditable. Value: a repeatable content factory that reuses the
same agents, memory, and approval controls as the rest of the platform.
Safety-first: disk exhaustion (a real past incident) is hard-gated before any
render; nothing publishes without explicit approval and a verified output; and
the system never claims a video was made or a post was published unless the
file exists and the receipt is real.

## Production hardening (M13.5)

SaathiOS now has the operational spine for controlled daily use: one-command
health/status/backup/restore/release checks, real disk-exhaustion protection,
stale-backend detection (which caused a real prior incident), and a proven
backup-and-restore drill. Cost/operational implications: local providers
(images, FFmpeg video, macOS narration) are free but macOS-only — Linux
production needs a configured cross-platform TTS before relying on narration.
Verdict is STAGING READY: safe for internal/pilot daily use; full PRODUCTION
readiness still needs authenticated browser verification and a real staging
deploy + rollback in production-representative infrastructure.

## CEO OS (M14)

CEO OS turns goals → priorities → missions → evidence → KPIs → decisions into
one operating layer over the whole platform. Portfolio model: businesses hold
goals + KPIs; a CEO mission is a real M10 agent run; risks/opportunities convert
into missions/projects. **Financial semantics (strict):** actual, estimated,
and forecast are always separate — an estimate is never shown as earned revenue,
and a KPI with no verified source reads "No verified data source" rather than a
guess. **KPI convention:** the verified dream-progress percentage (1.0 == 1% of
the 7.94M target) is reused unchanged. **Review cadence:** Daily Brief (real
data, evidence-tagged), weekly review persisted with provenance to memory.
Budget model: approved/committed/actual/forecast with variance + hard stop;
budget-increasing execution follows approval policy.

## M15.1 — Connectors reach staging

The connector platform now has a real, authenticated door: every business
action (send, publish, deploy, read email, check calendar) goes through one
governed API where the user owns their accounts, secrets are never shown, and
any side-effect needs a one-time approval bound to that exact action. Chat, the
agents, CEO OS, and Voice all reach the outside world through this single funnel
— nothing calls a provider behind the platform's back. Local tools (files, git)
are genuinely live; cloud accounts (Gmail, Calendar, Telegram, publishing) are
wired and waiting only on real credentials, and the system says so honestly
rather than pretending they work. A connector failure never turns into a fake
"zero" or "done" on a CEO dashboard — it stays visibly unavailable.

## M15.2 — Continuous security proof

SaathiOS now attacks itself. A built-in red-team harness runs a library of
adversarial scenarios — prompt injection, tricking an agent into misusing a
tool, replaying an approval, reading another user's data, extracting a secret —
against the real system on every run, and proves each attack is blocked with hard
evidence (not a model's opinion). On its first run it caught a genuine flaw where
one path could act on another user's account; that's now fixed and permanently
guarded by a test. The verdict is honest: the boundaries we can test here are
green; full sign-off still needs live adversarial tooling and real accounts on a
staging server.

## M15.3 — Connectors become enterprise-grade

The connector layer is now an enterprise integration platform: a real OAuth
sign-in flow with anti-forgery protections, exact-permission checks (an account
can only do what it was actually granted), automatic circuit breakers and rate
limits so one flaky provider can't cause a storm, and a clean error vocabulary
that never leaks secrets. Each connector's readiness is stated honestly —
implemented, configured, or actually live-tested — so nobody mistakes a wired-up
connector for a verified one. Cloud connectors (Gmail, Calendar, GitHub, Vercel)
are ready to validate the moment real credentials are supplied on staging; until
then they are marked environment-blocked, not "working". Live provider sign-off
and production use still require testing on real accounts in staging.

## M16 — One place to run everything

The Control Center is the single screen an operator opens to understand the whole
platform: what needs attention now (pending approvals, security findings, failing
release gates, blocked connectors), the live health of every subsystem, a
searchable index across connectors/accounts/approvals/executions, and recent
activity — each value tagged with where it came from and how fresh it is. It is
deliberately a window and a control panel, not a second brain: every action it
offers is executed by the real subsystem behind it, with the same approvals and
ownership checks. When a data source is down, it says so instead of showing a
comforting fake number. It is ready for staging use; full production sign-off
still needs authenticated browser verification and live provider data.

## M17 — SaathiOS as a digital worker

SaathiOS can now be pointed at a screen and operate software the way a person
does — see the window, find the button, click, type, verify the result — across
browsers and desktop apps, without custom code per app. Crucially it runs on the
same safety rails as everything else: it never assumes an action worked (it looks
again to confirm), destructive or costly actions (delete, purchase, send, deploy)
stop for approval, passwords and one-time codes never appear in its recorded
replays, and one user's session can never see another's. Today this is proven with
a deterministic simulator; driving real authenticated applications on a real
desktop is the next, credential-and-permission-gated step before it becomes a
pilot-ready digital worker.

## M17 hardening — safe by construction

Before SaathiOS touches a real screen it now demands explicit consent: a live
session that names exactly which apps, sites, and folders it may use, for how
long, and up to what risk — with a one-press emergency stop that instantly halts
it. It refuses to type passwords or one-time codes (it hands those moments back to
you and records only "entered by user"), never solves a CAPTCHA or bypasses MFA,
stays inside the folders you allowed, rejects booby-trapped page instructions, and
stops rather than guessing when the screen is uncertain. Every one of these
guarantees is proven by an automated attack suite. Driving real logged-in
applications on a real desktop is the next, permission-gated step.

## M17.1 — the browser digital worker is real

SaathiOS now genuinely drives a real web browser end-to-end: it opens an isolated
Chrome, loads a page, reads what's actually on it, fills fields, clicks, and —
crucially — confirms the result really happened before moving on, all while
refusing to type your password (it hands that moment back to you) and keeping its
recording clean of secrets. This ran for real, not in a simulator. Controlling
native Mac apps (Finder, TextEdit) is the next step and is intentionally gated
behind the macOS permission prompts only you can approve. This is a browser-scope
digital-worker pilot; full production still needs logged-in real-account workflows,
monitoring, and long-run stability.

## M17.2 — the Mac digital worker, honestly staged

SaathiOS now reads the real Mac: it lists the actually-running applications with
their true identities, refuses to be fooled by a look-alike window (a wrong
process is rejected), and captures the real screen — all through the same
governed pipeline. Actually operating Finder and TextEdit is deliberately gated
behind the one macOS Accessibility switch only you can flip, and a logged-in
desktop session; until then those steps report "permission needed", never a fake
success. So the native worker is staged and safe, with real read-level proof; the
browser worker (already piloted) and the native worker are tracked as separate
readiness levels so neither borrows the other's credibility.

## M17.3 — agents operate real apps, structurally

Instead of clicking around a screen, SaathiOS can now drive real applications
through their command-line "engines" — starting with FFmpeg, which it uses to
transcode a video and then independently re-checks the result really is a valid
video before calling it done. Only vetted, source-pinned harnesses run, each in a
locked-down process with no access to secrets or the wider filesystem; an agent
can suggest a new application harness but can never bless it as trusted itself —
that stays a human decision. External harness catalogs (like CLI-Anything's) can be
browsed but everything imported is untrusted until reviewed. This is a one-app pilot
(FFmpeg live); more apps and the install/update security come before production.

## M17.4 — one platform, many apps (safely)

The harness platform is now general: SaathiOS can discover which applications are
actually installed, install/update/roll-back/revoke their harnesses under strict
supply-chain checks (no installing from a random URL, binaries must live in
trusted locations, every update starts untrusted again), cap what a harness may
consume, and independently verify a wide range of outputs (documents,
spreadsheets, images, video, audio, archives) — refusing booby-trapped files like
zip bombs. Today FFmpeg is the one live, verified application; LibreOffice,
Blender and Kdenlive are wired and waiting only on being installed. Honest status:
staging-ready platform, one live app — more real apps come before a multi-app
pilot.

## M17.5 — two real apps, one safe path

The harness platform is no longer a one-app demo: SaathiOS now operates two real
applications — FFmpeg (media) and SQLite (databases) — through the exact same
governed, independently-verified path. For SQLite that means it can inspect a
schema, run read-only queries (writes are hard-blocked), and make a safe
reversible change, while refusing every dangerous trick (shell escapes, attaching
other databases, multi-statement injection). This is the multi-application pilot
threshold: the platform is proven to generalize across very different kinds of
software, safely. GUI apps (LibreOffice, Blender) still need installing before
they join.

## M17.6 — three real apps, three categories

SaathiOS now safely operates three genuinely different real applications through
one governed path: FFmpeg (video/audio), SQLite (databases), and jq (transforming
JSON — exactly the shape of data connectors and APIs return). Each runs with the
same guarantees: locked-down process, no secret access, and an independent check
that the result is real (a valid video, an intact database, well-formed JSON) —
never taking the tool's word for success. This breadth across categories is what
makes the harness platform a real multi-application pilot rather than a one-trick
demo. Installing GUI apps (LibreOffice/Blender) is the next optional step.

## M17.9 — runs you can trust, even when things crash or collide

When SaathiOS runs real software for you, it now keeps a durable, tamper-resistant
ledger of every run — who started it, what state it's in, when it last checked in,
and how it ended. The upgrade matters for reliability: two processes can never
both "claim" the same job, a finished job can never be silently flipped back to
running, and if the machine crashes mid-run, the interrupted job is reconciled
exactly once into clear "crash recovered" evidence instead of vanishing into an
unknown state. Recovery is careful by design — it never re-runs work that isn't
safe to repeat and never touches a job whose process is still alive. Old records
from the previous system are migrated safely (backed up first, reversible, nothing
lost). Operators get a maintenance view of active runs, stuck-run alerts, and a
one-command health check; everyday users see only their own runs, and no private
command details, output, or secrets are ever exposed. This is the difference
between "it usually works" and "we can prove what happened" — the foundation for
running long, important tasks unattended. Still ahead before production: proving it
under many simultaneous users, and a live monitoring/alerting dashboard.

## M17.10 — SaathiOS notices when a task gets stuck

Running real work unattended only matters if someone notices when a job hangs.
SaathiOS now watches its own long-running tasks: if a job stops checking in, or was
told to cancel but won't stop, or its process quietly vanished, the system raises a
clear, de-duplicated alert — once per problem, not a flood — and surfaces it on the
control center's "needs attention" list, ranked by severity. Alerts clear
themselves the moment the job recovers or finishes, so the list always reflects
reality. An operator can acknowledge an alert (recorded with who did it), and a
vanished job is automatically reconciled without ever re-running work or touching a
job that's still alive. Everyday users see only their own alerts, and no private
command details are exposed. This is the foundation of "run it and trust it" —
the safety net before autonomous operation. Still ahead: sending alerts out to
email/Slack, running the watcher on a schedule, and a full incident drill. This
milestone touches nothing financial and enables no autonomous trading.

## M17.11 — alerts that actually reach someone, reliably

M17.10 let SaathiOS notice a stuck task; M17.11 makes sure that notice actually gets
delivered — durably, once, and with retries if the first attempt fails. Every alert
becomes a tracked delivery record: it is sent through a configured channel, retried
on a fixed, predictable schedule (immediately, then 1, 5, 15, 60 minutes) up to five
times, and if it still can't get through it becomes a clearly-marked "delivery
failed" item an operator can retry by hand. Nothing is delivered twice, even if two
background workers run at once or the machine restarts mid-send. If the underlying
problem resolves or an operator acknowledges it, pending notifications are quietly
suppressed instead of nagging. A built-in local delivery channel works with no
accounts or credentials at all, so the whole safety net functions offline;
connecting external channels like email or Telegram is a later, optional step and
fails safely when not configured. An opt-in scheduler can run the watcher on an
interval. This milestone touches nothing financial and enables no trading — but the
delivery plumbing is built so future Trading Guardian alerts could ride the same
reliable path, advisory-only.

## M17.12 — chaining real tools into one governed workflow

The four real applications SaathiOS can already drive safely — FFmpeg, SQLite, jq,
and zip — could until now only be run one at a time. M17.12 lets them be chained
into a single, ordered workflow: do step one, hand its result to step two, and so
on. The chain is deterministic and honest — if any step fails, is uncertain, or
would need approval it hasn't been granted, the whole workflow stops there and the
later steps never run (no half-finished, misleading results). Every step's output
stays inside one private scratch folder for that run; a step can never reach outside
it, even by trying to name a file with an escape path. Each run is recorded so you
can see exactly which steps succeeded, which one failed, and why — without any raw
commands, file contents, or secrets ever being exposed. A failed workflow shows up
in the Control Center for the owner (and only the owner) to see. This proves out the
"AI Studio" idea — real multi-tool jobs — on top of the execution reliability built
over the last four milestones. It adds no new engine and changes nothing financial:
approval gates are made stronger here, never weaker. Still to come: running steps in
parallel, resuming a failed workflow from where it stopped, and accepting
externally-authored workflow definitions.

## M17.13 — one objective, done safely end to end

Until now you had to think in tools and steps. M17.13 lets you think in OBJECTIVES:
"make today's IELTS lesson", "produce the daily CEO brief", "run the kitchen
inventory audit". Each objective is a Mission — a named job with its own typed
inputs (a date, a difficulty, a language, a publish yes/no), an owner, and a clear
rule about whether a human must approve it before it runs. A Mission never touches a
tool itself; it hands the work down to the governed workflow built last milestone,
which hands each step to the sole safe executor. The inputs are checked before
anything runs, so a bad or missing value is caught up front, not halfway through. A
mission is marked done ONLY if every step actually succeeded — there is no
half-finished "sort of worked". If the work fails, the mission fails cleanly and
shows up for its owner (and only its owner) in the Control Center, with the reason
but never any raw commands or secrets. Approval is honest: a mission that needs
sign-off cannot start until it gets it. Missions are reusable through templates —
define "daily crypto analysis" once and stamp out a fresh, auditable instance each
day. A failed mission can be retried, which safely starts a brand-new instance
rather than quietly reopening a closed one, so the history stays trustworthy. This
is the layer that turns SaathiOS from "a set of safe tools" into "an assistant you
give objectives to". It adds no new engine and changes nothing financial — approval
gates are strengthened here, never weakened. Still to come: automatic scheduling and
event triggers, running missions in parallel, and accepting externally-authored
mission definitions.

## M17.14 — recurring missions that run on time, exactly once

SaathiOS can now run APPROVED missions on a schedule — a one-time run, an interval,
a daily time, or a weekly day-and-time — and can also start a mission in response to
a small set of TRUSTED internal events (for example, "a pipeline failed" or "the
daily rollover happened"). Each due time creates exactly one piece of work, and each
piece of work creates at most one mission: FAILURES DO NOT CREATE SILENT DUPLICATE
WORK. If the system restarts in the middle of a scheduled run, it safely resumes the
existing work rather than starting a second copy. Scheduling only decides WHEN a
mission is due — it never changes how the mission runs: SCHEDULED WORK STILL RESPECTS
APPROVALS. A scheduled mission that needs sign-off stops and waits for it; it is
never auto-approved just because it was scheduled. Everything is owner-scoped and
shows up safely in the Control Center — no raw event data, commands, or secrets.

What it unlocks, in plain terms:
- **IELTSAlert**: "build today's practice set every morning at 6:00" — created once
  per day, on time, verified end to end.
- **CEO OS**: "produce the daily CEO brief on a schedule, or the moment the review
  is requested" — and if it needs approval, it waits for you.
- **Cafeteria (HCG) reporting**: "run the closing/inventory report each evening" —
  once per evening, with a clear record of success or the reason it failed.
- **HCG research**: "kick off a research mission when an upstream job finishes" —
  from a trusted internal event, deduplicated so one event means one mission.

Two things stay deliberately off: PRODUCTION AUTO-SCHEDULING IS STILL NOT ENABLED BY
DEFAULT (the recurring runner is opt-in for local use; no always-on server job is
provisioned), and LIVE TRADING IS NOT ENABLED — scheduling a mission can never turn
advisory permission into trading permission. It adds no new engine and changes
nothing financial.

## M17.15 — long jobs no longer restart from zero after a safe hiccup

Some SaathiOS jobs have several steps — build a file, verify it, package it, publish
it. Until now, if a late step hit a temporary snag, the ENTIRE job had to start over,
repeating work that already succeeded. M17.15 fixes that: LONG WORKFLOWS NO LONGER
NEED TO RESTART FROM ZERO AFTER A SAFE, RECOVERABLE FAILURE. Every step that
succeeds is independently verified and saved as a trustworthy checkpoint. When the
job resumes, it REUSES COMPLETED VERIFIED WORK ONLY WHEN IT IS UNCHANGED AND INTACT,
and picks up from the first step that still needs doing. If a saved output was
deleted or altered, the system notices — TAMPERED OR MISSING OUTPUTS FORCE A SAFE
RERUN of the step that produced them (and everything after it), rather than trusting
a bad file. And APPROVALS REMAIN MANDATORY: resuming or retrying a job never grants
permission — a step that needs sign-off still waits for it. Retries happen only for
genuinely temporary problems, a bounded number of times, then stop.

What it unlocks, in plain terms:
- **IELTSAlert video generation**: a multi-step render that stumbles on the packaging
  step resumes from packaging — the verified audio/segments aren't rebuilt.
- **Cafeteria (HCG) reports**: an evening report that hits a momentary file lock
  retries just the affected step, not the whole report.
- **CEO OS**: a brief that fails late resumes from where it stopped, and still waits
  for approval if approval was required.
- **HCG research**: a long research pipeline continues from its last verified stage
  after an interruption, without redoing completed, verified work.

Live trading remains disabled — recovery adds no trading ability and can never retry
or resume a trade. It adds no new engine and changes nothing financial.

## M17.16 — independent work now happens at the same time, still fully checked

Until now a workflow ran one step after another, even when two steps had nothing to
do with each other. M17.16 lets INDEPENDENT WORK RUN AT THE SAME TIME. A workflow can
now fork into two or more branches that run together and then rejoin at a single
packaging step — for example, build a dataset once, then generate a report AND render
a media asset in parallel, then bundle both.

What does NOT change is the checking. Every branch is still verified separately, by
the same independent checks as before. Faster execution does not reduce verification.
And the safety is stricter, not looser:

- **One failed branch prevents a misleading final result.** If either branch fails,
  the final packaging step never runs — you never get a "finished" bundle that is
  quietly missing half its contents.
- **Verified successful branches can be reused.** If one branch fails and is retried,
  the branch that already succeeded is not redone — only the failed branch runs again.
- **Approval stays per step.** One branch running does not approve another; a branch
  that needs approval blocks the join until it is granted.

Examples:
- **IELTSAlert content generation**: generate the lesson text and the practice audio
  as two parallel branches, then package them together once both are verified.
- **CEO reports**: pull the numbers once, then build the financial section and the
  narrative section at the same time, then assemble the final brief.
- **Cafeteria reporting**: run the inventory summary and the sales summary in
  parallel, then combine them into one verified daily report.
- **HCG research**: gather two independent source sets concurrently, then merge them
  into one verified research bundle.

Public production and live trading remain disabled. This is a bounded, acyclic
workflow — not an unrestricted workflow engine — and it adds no financial ability.
