# M69 — Autonomous Mission Runtime Foundation

Date: 2026-07-28
Baseline: `a4cb5c4d872a3edf048d52b7cd62bf9346703613`
Implementation commit: `5d356b65fc5938047d597e3e0cd704562b318dbb`
Verdict: `M69_COMPLETE`

## Result

M69 establishes the durable, tenant-scoped control-plane foundation for autonomous
missions without adding an execution engine. The existing platform mission record
remains authoritative. Additive runtime tables and one service persist a validated
Mission → Goal → Phase → Milestone → Task → Subtask hierarchy, task dependencies,
evidence, decisions, checkpoints, reviews, and certifications.

## Contracts

- Task states: `PENDING`, `READY`, `RUNNING`, `WAITING`, `BLOCKED`, `FAILED`,
  `COMPLETED`, `CANCELLED`, and `SKIPPED`, with fail-closed transition maps.
- Agent abstractions: Planner, Architect, Implementer, Reviewer, Test, Browser,
  Documentation, and Certification agents.
- DAG: stable node identifiers, duplicate/self/unknown-edge rejection, Kahn cycle
  validation, priority ordering, and dependency-driven readiness/blocking.
- Budgets: estimated effort, elapsed seconds, token estimate, commits, tests, browser
  runs, cycles, and no-progress cycles with finite upper bounds.
- Completion: every declared verification check needs passing evidence; tasks marked
  for review also need an approved independent review.
- Checkpoints: mission state, completed/pending tasks, phase/task/agent, resource
  usage, commit/rollback SHAs, test/browser status, blockers, and a deterministic
  SHA-256 snapshot hash.
- Dashboard read model: health, progress, active phase/task/agent, task counts,
  evidence context, warnings, blockers, ETA, resource usage, and verification state.

## Architecture reused

- `PlatformStore` and its existing `missions` authority.
- `PlatformExecutionContext`, platform RBAC, project/workspace/org isolation, and
  centralized audit.
- M17 graph concepts and M20 checkpoint semantics as design evidence.
- `PlatformAgentRuntime` / `ExecutionGateway` are reserved as the only dispatch path
  for M70; M69 deliberately performs no tool dispatch.

## Verification

- New focused suite:
  `python -m pytest -q tests/test_m69_mission_runtime_foundation.py` — **4 passed**.
- Related backend regression (M17 mission engine, M20 engineering orchestrator, M52
  platform runtime, M61 workflow persistence, M69) — **124 passed**.
- Frontend regression: `npm test` — **180 passed**.
- Retained unified-shell browser certificate on loopback production build:
  **PASS**, 21 hard + 12 state + 6 responsive + 3 accessibility gates, zero page
  errors, zero unexpected console errors, and zero framework overlays.
- Production-code secret scan using `saathi.repair.secrets_scan.scan_files` — **clean**
  across five changed Python implementation files. The test-only conventional
  `GoodPassw0rd!` fixture is detected by the generic assignment heuristic and is not a
  credential.
- `compileall` and `git diff --check` — **pass**.
- Ruff was not available in the repository virtual environment, so no Ruff result is
  claimed.

## Security review

Planning requires `mission.write`; starting and task transitions require
`mission.run`; reads require `mission.read`. Organization, workspace, and optional
project scope fail closed. Secret-shaped nested input fields are rejected before
persistence. Inputs, hierarchy counts, retries, priorities, strings, budgets, and
parallelism are bounded. SQL values are parameterized. No credentials, network
calls, shell execution, provider calls, financial authority, or production changes
were introduced.

## Limitations and next milestone

M69 stores and validates state but does not yet dispatch agents, enforce budget stops
during execution, retry failed work, pause/resume/cancel a mission, or recover
in-flight work. M70 owns those behaviors and must route all executable tasks through
the existing `PlatformAgentRuntime` and `ExecutionGateway`.

No push, merge, deployment, DNS, credential, production database, external provider,
or production infrastructure change was made.
