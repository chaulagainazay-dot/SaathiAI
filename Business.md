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
