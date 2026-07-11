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
