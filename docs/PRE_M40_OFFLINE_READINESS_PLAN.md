# PRE-M40 Offline Readiness Series

**Created:** 2026-07-19
**Starting checkpoint:** `9fad03c` (feat(security): complete M39 offline validation framework)
**Branch:** `milestone/m7-security-engine`

## Why this series exists

M39 offline implementation is complete and certified. Its **live** exercises are
BLOCKED pending an operator-supplied disposable secret **reference**. The canonical
M40 contract requires successful M39 live validation, so M40 **cannot** start.

This series completes every feasible non-live engineering task so that, the moment
the operator supplies a disposable secret reference, live validation and the
subsequent canary decision are turnkey. Milestones use the `M39.x` numbering
(offline readiness extensions) — they do **not** claim M40 semantics and do **not**
alter any authority state.

## Non-negotiable authority state (unchanged for the entire series)

- LIVE PROVIDER CERTIFICATION: **NOT GRANTED**
- CANARY: **NOT GRANTED**
- ACTIVE: **NOT GRANTED**
- M40 PRODUCTION AUTHORIZATION: **NOT GRANTED**
- Trading Guardian: **UNCHANGED / UNENGAGED**

Every milestone is additive, bounded, tested, documented, committed, and
independently reversible. No milestone resolves or uses a live secret. All
live-dependent fields remain one of: `NOT_EXERCISED`, `BLOCKED_OPERATOR_SECRET_REQUIRED`,
`BLOCKED_OPERATOR_ACTION_REQUIRED`, `OFFLINE_ONLY`, `SIMULATED_NOT_LIVE`.

## Repository inventory (already present — do NOT duplicate)

- `saathi/credentials/m39.py` — preflight, secret-reference qualification, single/multi
  live runners, kill switch, external-revocation record, canary eligibility evaluator.
- CLI `m39-*` (10 subcommands): preflight, authorize-live-validation, qualify-secret-reference,
  run-live-single-session, run-live-multisession, interrupt-session, recover-session,
  confirm-external-revocation, evaluate-canary-eligibility, emit-m39-evidence.
- Runbooks: `M39_LIVE_VALIDATION_RUNBOOK.md`, `M39_INTERRUPTION_AND_RECOVERY.md`,
  `M36_SECRET_SOURCE_RUNBOOK.md`, `DISASTER_RECOVERY_RUNBOOK.md`, `M26_INCIDENT_RESPONSE.md`.
- Provider contracts: `M32_PROVIDER_ADAPTER_CONTRACT.md`, `M37_PROVIDER_MODEL.md`.
- Correlation IDs, deterministic error taxonomy, aggregate/per-session budgets already exist.

## Identified offline gaps → milestone map

| ID | Objective | Gap addressed | Phase 3 area |
|----|-----------|---------------|--------------|
| **M39.1** | Operator live-validation dry-run planner: execution plan, human-readable command preview, secret-backend availability check (no resolution), revocation checklist generator | No dry-run/preview/checklist/backend-availability surface exists | A |
| M39.2 | Live-test orchestration simulation coverage: fixture-driven paths for throttle, network failure, malformed response, auth denial, kill-switch, secret-resolution failure (SIMULATED_NOT_LIVE) | Simulation coverage gaps for live-only failure modes | B |
| M39.3 | Canary-readiness framework completion: immutable prerequisite checks, operator approval record format, rollback triggers, exit criteria (still CANARY_NOT_GRANTED) | Evaluator exists; decision-record + trigger scaffolding incomplete | C |
| M39.4 | Deployment & rollback preparation for the M39 external-provider surface: config validators, release checklist, rollback script, backward-compat checks (no execution) | No M39-surface deploy/rollback artifacts | D |
| M39.5 | Monitoring & incident response: structured audit-event contracts, alert definitions, stuck-run/budget-exhaustion/secret-failure detection, incident + recovery runbooks (local transports only) | M39-surface observability contracts missing | E |
| M39.6 | Security & adversarial test expansion: raw-secret injection, ref confusion, path traversal, SSRF-like endpoint manipulation, scope escalation, stale-lease reuse, double cleanup, evidence tampering (synthetic creds only) | Deterministic negative coverage can be broadened | F |
| M39.7 | Reproducibility & clean-environment validation: isolated-worktree checkout, byte-for-byte double evidence regeneration, dependency validation, CLI-contract checks | No formal reproducibility harness for M39 | G |
| M39.8 | Final operator package: architecture, trust boundaries, setup guide, live-validation checklist, procedures, evidence interpretation, residual risks, go-live checklist | Consolidated operator package not assembled | H |

Milestones are executed in order but each is independently reversible. The series
stops when remaining work genuinely requires operator-controlled live access.

## Selection rule per milestone

1. Inspect repository evidence.
2. Select exactly one bounded objective (highest safe value first).
3. Implement only that objective; preserve M31–M39 architecture.
4. Add/update tests; run narrowest tests, then regression, then leak scan.
5. Update canonical docs + evidence; commit; record rollback commit.
6. Continue to next milestone unless blocked.
