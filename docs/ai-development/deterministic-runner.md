# Deterministic Agent Runner

**Milestone:** M354
**Module:** `saathi/agentdev/runner.py`
**Commands:** `runner plan` · `runner run`
**Classification:** `deterministic`

M351 ships one hard-coded mission narrative. This is the engine underneath it:
an execution layer that runs *any* mission plan by driving scripted handlers
through one uniform contract, and records what happened while doing so.

No prompts. No model. No reasoning. A handler is a Python function of its
inputs.

---

## 1. The seven-phase contract

Every step passes all seven phases, in order. There is no path that skips one,
and a step that fails records which phase it failed in.

| Phase | What happens | Fails when |
|---|---|---|
| `receive` | Resolve the declared input artifacts and the author's role contract | An input step never ran, an input artifact is missing, the agent is not a declared role |
| `process` | The handler computes a body — pure, no store, no clock, no filesystem | No handler is registered, or the handler returns something other than a mapping |
| `produce` | Build the artifact, running full M347 schema validation | The handler tried to set an envelope field, or the artifact is malformed |
| `record` | Persist through `ArtifactStore` (atomic write, `.bak` retained) | The write fails |
| `verify` | Read it back and compare a SHA-256 digest of the canonical form | The artifact is unreadable, the kind changed, or the digest differs |
| `handoff` | Name the next agent and the required next action | The named agent is not a declared role |
| `finish` | Stamp timing and index the output for later steps | — |

Gate, advance and verdict steps run the same seven phases with the same
meanings; only the work inside them differs.

## 2. Four step actions

| Action | Effect | The check that cannot be skipped |
|---|---|---|
| `agent` | One participant produces one artifact | The role must hold the capability the artifact kind requires |
| `gate` | The real `GateEngine` evaluates and records a gate | No self-approval, evidence present, right kind, right author |
| `advance` | The mission moves to a declared state | The current state's exit gates must have passed |
| `verdict` | The CEO records the terminal verdict | Only the CEO may; a full approval is refused while a disagreement stands |

## 3. The eight participants

| Specified | Role id | Produces |
|---|---|---|
| CEO | `ceo` | `mission_intake`, `executive_decision`, `final_synthesis` |
| Manager | `program-manager` | `task_assignment`, `implementation_handoff` |
| Research | `research` | `research_findings` |
| Architecture | `architecture` | `architecture_decision` |
| Security | `security-governance` | `security_review`, `meeting_minutes` |
| Testing | `testing-verification` | `verification_report` |
| Documentation | `documentation` | `documentation_update` |
| Code Review | `code-review` | `code_review` |

No new role was invented; all eight already existed in `data/roles.json`.

One artifact kind *was* added. The Documentation Agent held
`author_documentation` with no kind it could write — every other capability had
one. `documentation_update` closes that, making seventeen kinds. Letting
documentation masquerade as research findings was the alternative, and it was
worse.

## 4. Determinism, and its one seam

Two runs of the same plan produce byte-identical artifact content. The test
asserts this against SHA-256 digests of the real stored files, not a summary.

The seam is `artifact_id`. M347 mints it from `uuid4`, which would make two runs
incomparable, so the runner derives it from the step index instead:

```
deterministic_artifact_id("research_findings", "dmrunner01", 4) == "rese_dmrunner01_04"
```

The digest deliberately ignores `created_at` and `updated_at` — a clock is not
content — and nothing else.

## 5. What a handler may and may not do

A handler receives a `HandlerContext` with exactly three fields: the plan, its
own step, and its resolved input artifacts. It returns the artifact *body*.

The envelope — `artifact_id`, `mission_id`, `kind`, `authoring_agent`,
`repository_sha`, `title`, `required_next_action`, `status` and the clocks —
belongs to the runner. A handler that returns one is refused by name at
`produce`, with the offending fields in the failure detail. That is what stops
a handler forging an author, a mission or a SHA, and it is the reason the M356
model-backed handler gains no authority by being a model.

`override_handler()` is the seam M356 uses to replace exactly one participant.
The replacement receives the same context, returns the same shape, and is
subject to the same refusal.

## 6. The reference mission

`runner run` executes a thirty-step plan: intake → decomposed → research →
design → security review → implementation ready → in implementation →
verification → executive decision → closed, passing nine gates on the way.

Measured on the development host (Apple Silicon, 8 GB):

| | |
|---|---|
| Steps | 30 |
| Gates passed | 9 |
| Artifacts produced | 11 |
| Self-approvals | 0 |
| Wall clock | ~20 ms |
| Slowest phase | `record` (~12 ms — atomic writes with `.bak` retention) |

Full trace: `docs/evidence/m352_m359/DETERMINISTIC_RUNNER_TRACE.json`.

## 7. What this does not establish

- **Nothing about a model.** Handlers are Python functions. The trace says so in its own `limitation` field, and `model_used` is null.
- **Nothing about code correctness.** The runner drives the governance path; it does not compile, test or execute the work an implementation step describes.
- **No worktree is created.** Code-bound artifacts name a worktree and branch because the schema requires it. `runner` never calls git; worktree creation stays behind `WorktreeManager` and its disabled-by-default flag.
- **No shell, credential or network.** A test greps the module for `subprocess`, `os.system`, `socket`, `urllib`, `requests`, `http`, `getenv` and `environ`, and asserts none appears.
