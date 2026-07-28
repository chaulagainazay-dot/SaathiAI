# M71 — Authenticated Mission Runtime API and Dashboard

Date: 2026-07-28
Baseline: `072fea7` (M70 certification state)
Implementation commit: `fb338d46341390db685155b7c3ff60a12af33bae`
Verdict: `M71_COMPLETE`

## Result

M71 exposes the Autonomous Mission Runtime through authenticated, tenant-scoped
platform APIs and renders its persisted state inside the existing SaathiOS Mission
Control shell. The browser is a read-only operator surface: it displays backend
mission health, progress, phase, task, agent, evidence, warnings, blockers, ETA,
resource use, task dependencies, and recovery checkpoints without gaining execution
or approval authority.

## Authenticated API

The existing `/api/v1/platform` router now provides:

- mission-runtime dashboard and per-mission detail reads;
- bounded plan creation and finite run-until-stop;
- pause, resume, cancellation, and interruption recovery;
- explicit approval attachment to a waiting task;
- append-only evidence, independent review, and checkpoint recording.

All routes resolve the existing platform token to `PlatformExecutionContext`; the
service then enforces organization/workspace/project scope and `mission.read`,
`mission.write`, or `mission.run`. Missing and cross-scope missions share the same
`NOT_FOUND` response. Validation, state, resource, review, verification, and approval
stops are structured fail-closed responses. The run request is capped at 50 cycles
and a one-hour request timeout.

## Unified-shell Mission Dashboard

- `/platform/missions` merges backend runtime summaries into existing mission cards.
- `/platform/missions/[missionId]` shows governed execution lineage, runtime health
  and progress, active phase/task/agent, budget use, commits, test/browser status,
  dependency-aware tasks, evidence, warnings/blockers, and checkpoint history.
- Missing runtime state is shown as an honest “no autonomous plan” state.
- A pure normalizer rejects malformed or absent data and never infers completion,
  health, evidence, or execution state in the browser.
- The page exposes no run, auto-approve, or direct gateway control.

## Architecture reused

- Existing platform Mission, Identity, Workspace, Project, RBAC, Audit, Evidence, and
  Approval authorities.
- M69 MissionRuntimeService/repository and backend dashboard read model.
- M70 MissionRuntimeOrchestrator and bounded role agents.
- `PlatformAgentRuntime` remains the only agent execution runtime and
  `ExecutionGateway` remains the only registered-tool executor.
- Existing spatial shell, navigation, status primitives, platform client, and design
  tokens; no second dashboard or design system.

## Verification

- New backend API suite — **3 passed**.
- Related M17/M20/M52/M61/M69/M70/M71 backend regression — **135 passed**.
- Frontend unit regression — **183 passed**, including 3 mission-runtime normalizer
  contracts.
- ESLint — **pass** with zero warnings.
- Next.js optimized production build — **pass**, including both Mission Control
  routes.
- Isolated authenticated production-build browser certificate — **PASS**: 21 hard,
  2 responsive, and 2 accessibility gates; zero page, console, or hydration errors.
- Browser evidence:
  `docs/platform/m71_evidence/M71_BROWSER_CERT.json` and three desktop/mobile
  screenshots.
- Production secret scan — **clean** across 13 changed backend/frontend
  implementation files.
- Python compile and `git diff --check` — **pass**.

The first isolated browser attempt correctly rejected the unauthenticated legacy
connector poll and surfaced a CORS console error. The harness was corrected to issue
a harness-only legacy shell session alongside the platform session. The final
certificate contains no credential material and all shell requests are authenticated.

## Security and regression review

No raw token is persisted in mission state, evidence, decisions, checkpoints,
screenshots, or the browser report. Planning rejects nested secret-shaped fields.
Run cycles/timeouts and request collections are bounded. Invalid role-agent review
input becomes a structured validation failure. API error paths do not disclose
whether another tenant owns a mission. The browser consumes server state and cannot
call `ExecutionGateway`, silently approve, or manufacture a successful result.

No trading, financial, connector, cloud, deployment, production infrastructure, or
future application-module authority was added. Existing platform and frontend
regressions remain green.

## Limitations and next milestone

The dashboard is intentionally observational. Interactive mission execution remains
an authenticated API/orchestrator concern, and human approvals remain in the
Approval Center. Execution is single-host and synchronous at the bounded cycle
boundary. M72 adds the final certification gate, full-repository regression/security
review, authoritative architecture/capability documentation, and the terminal
`MISSION_RUNTIME_COMPLETE` verdict.

No push, merge, deployment, DNS, credential, production database, external provider,
or production infrastructure change was made.
