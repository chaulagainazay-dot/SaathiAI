# SaathiOS Delivery Constitution

> Governing law for spec-driven delivery. Every milestone spec, plan, and task
> set is checked against these articles at the convergence gate. Amendments are
> version-bumped; this is v1.0.

## Article I — Single Execution Boundary
No feature, connector, agent, or workflow performs an external side effect
except through the ExecutionGateway. Any code that instantiates a provider
client directly after migration is a bounded, recorded transitional exception —
never a silent one.

## Article II — Least Privilege & Approval Binding
Risk is classified 0–4. Actions at risk ≥ 3 (external side effect) require an
approval bound to the EXACT action (tool + account + normalized input). Risk 4
(high impact) is manual-only. A connector may never downgrade its capability's
risk floor. Approvals are single-use and expire.

## Article III — Secrets Never Travel
Secrets never enter prompts, logs, memory, checkpoints, reports, Git, API
responses, or error strings. Credentials are stored as references (backend +
key name), resolved in-process only, and discarded.

## Article IV — Honest Evidence
Claims are separated into: implemented, automated-tested,
deterministic-adapter-tested, live-connector-tested, browser-tested,
convergence-verified, environment-blocked, unverified. Live integration is
never faked. A connector without credentials in the environment reports
environment-blocked, not "healthy".

## Article V — Idempotency & Uncertainty
Repeated actions with the same idempotency key are replayed, not re-run.
Uncertain side effects and non-idempotent failures are NEVER auto-retried.

## Article VI — Reuse Over Rebuild
Existing systems (M8 chat, M9 memory, M10 agents, M12 voice, M13 studio, M14
CEO OS, execution gateway) are integrated, not duplicated. No upstream repo is
vendored wholesale without a documented reason; copied code preserves its
license.

## Article VII — Traceability
Every requirement has a stable ID. Every requirement maps to an implementing
artifact and a test. The convergence gate fails if any requirement is
unmapped or untested.

## Article VIII — Reversible Delivery
Local commits only until explicitly released. No history rewrite. No push or
deploy without explicit instruction. Start/end commits, tree status, and
rollback are always reported.
