# M70 — Mission Decisions, Agents, Dispatch, and Recovery

Date: 2026-07-28
Baseline: `354fa88` (M69 certification state)
Implementation commit: `a628b43764481559697942fbb1f0d5782ff99718`
Verdict: `M70_COMPLETE`

## Result

M70 turns the persisted M69 control plane into a finite execution loop while retaining
the existing execution authority. It can choose dependency-ready work, run independent
safe tasks concurrently, route each role task through `PlatformAgentRuntime`, stop for
human approval, resume the same execution, retry only confirmed transient failures,
pause/resume/cancel, reconcile interrupted work, collect execution evidence, and stop
at resource or safety boundaries.

## Agent framework

The fixed role directory contains PlannerAgent, ArchitectAgent, ImplementerAgent,
ReviewerAgent, TestAgent, BrowserAgent, DocumentationAgent, and CertificationAgent.
These are responsibility labels and dispatch adapters only. They do not create
identities, bindings, permissions, credentials, connectors, or executors. All initial
dispatches call `PlatformAgentRuntime.execute_context`; approval/recovery continuation
uses its existing resume path; cancellation uses its cancellation path.

## Decision and queue policy

- Dependency-ready tasks are ordered by priority and plan position.
- A non-concurrency-safe task runs alone; otherwise a batch is bounded by
  `max_parallel_tasks`.
- Tasks without a registered `tool_id` stop at `BLOCKED_EXTERNAL_INPUT`; no work is
  fabricated.
- The scheduler returns explicit dispatch/wait/review/approval/complete/stop decisions
  and one of the bounded stop conditions.
- Mission cycles, elapsed time, estimated tokens/effort, commits, tests, browser runs,
  and no-progress cycles are tracked. Predicted budget overflow blocks before dispatch.
- A finite `run_until_stop` ceiling prevents unbounded scheduling loops.

## Failure, retry, and approval

- Only `FAILURE_CONFIRMED` plus an allowlisted transient code can retry.
- Retry count is task-bounded, backoff is exponential and capped at five minutes, and
  every retry decision is durable.
- Unknown outcome, unknown side effect, unclassified exception, missing authority,
  permission/binding denial, or unsafe approval state fails closed.
- Approval-required execution becomes a durable WAITING task and mission. Attaching an
  approved, scoped, matching platform approval moves the task to READY; the runtime
  resumes and consumes the original execution rather than creating another one.

## Pause, cancellation, checkpoint, and recovery

- Authorized pause/resume decisions are audited and checkpointed.
- Cancellation marks mission intent, asks the canonical runtime to cancel linked
  executions, and does not claim completion until cancellation is confirmed.
- Recovery locates the execution by durable link or deterministic idempotency key.
  A pre-dispatch interruption may resume with a fresh token. Approval waits remain
  approval waits. Recorded dispatch is reconciled to PAUSED and blocked for review;
  it is never replayed. Confirmed terminal results are recovered without inventing
  success.
- Each cycle/control/recovery boundary writes the M69 checkpoint snapshot.

## Architecture reused

- M69 mission service/repository and PlatformStore state.
- `PlatformAgentRuntime` for binding, context, idempotency, approval, cancellation,
  recovery classification, and result persistence.
- `ExecutionGateway` remains the sole registered-tool executor and is not imported by
  mission-runtime code.
- Existing platform RBAC, approval records, audit, tool registry, and outcome contract.

## Verification

- New M70 suite — **8 passed**: real gateway-path dispatch, safe parallel roles,
  approval wait/resume, bounded retry, verification promotion, predicted budget stop,
  uncertain-dispatch recovery, and pause/resume/cancel/missing-adapter stops.
- M69 + M70 + M52 focused runtime regression — **28 passed**.
- Related M17/M20/M52/M61/M69/M70 backend regression — **132 passed**.
- Frontend retained regression — **180 passed**.
- Retained unified-shell production browser certificate — **PASS**: 21 hard, 12 state,
  6 responsive, and 3 accessibility gates; zero page errors, unexpected console
  errors, and framework overlays.
- Secret scan across eight changed production Python files — **clean**.
- Compileall and `git diff --check` — **pass**.
- Ruff remains unavailable in the repository virtual environment; no Ruff result is
  claimed.

## Security review and limitations

The scheduler requires `mission.run`; all service reads/writes retain M69 tenant and
project scope. Approval references must be approved, unconsumed, tool-matching, and
mission/project scoped; PlatformAgentRuntime revalidates and atomically consumes them.
No raw token is persisted. A token is accepted only ephemerally for explicit
resume/cancel/recovery. No direct gateway, connector, shell, network, financial, live
trading, or production path was added.

M70 is checkout-local and synchronous at the cycle boundary. Parallel tasks use a
bounded thread batch, while the dashboard exposes a single representative active
agent/task plus complete task states. Distributed scheduling and background workers
remain outside this goal.

No push, merge, deployment, DNS, credential, production database, external provider,
or production infrastructure change was made.
