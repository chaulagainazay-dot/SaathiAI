# SaathiOS Multi-Agent Development Environment — Overview

An offline-first environment in which specialised development agents receive
bounded missions, research independently, deliberate in recorded meetings,
challenge each other with evidence, and produce decisions that a human owner
can audit.

**Milestones:** M344–M351 · **Package:** `saathi/agentdev/` · **Status:** foundation

## What this is not

| Not this | Because |
|---|---|
| A replacement for the Mission Engine | Product missions stay in `saathi/missions/`. Development missions are a different noun with a different lifecycle. |
| A second engineering orchestrator | `saathi/engineering/` (M20.0–M20.7) keeps sole ownership of coding-agent sessions, approvals, session ledger and integrity evidence. `agentdev` calls into it. |
| A second governance engine | Authority levels come from `saathi.safety.SafetyLevel`. There is no parallel enum. |
| A port of ECC | ECC is a read-only reference toolkit at `~/dev-toolkits/ECC`. No ECC file, module, hook, dependency or managed artifact exists in this repository. |
| A production capability | Nothing here is reachable from the product surface. All authority flags are false by default and several cannot be enabled by environment at all. |

## Four distinct agent populations

Confusing these is the most likely way to misread this system.

| Population | Where | Purpose | Governed by |
|---|---|---|---|
| **Runtime product agents** | `saathi/agent_registry.py`, `saathi/agents/` | Serve users at request time | `saathi/safety.py` |
| **Coding-agent sessions** | `saathi/engineering/` | Execute one backlog item under supervision | `engineering/settings.py`, bound approvals |
| **Development agents** | `saathi/agentdev/` (this milestone) | Deliberate over a development mission | `agentdev/roles.py`, gates, worktree scopes |
| **ECC agents** | `~/dev-toolkits/ecc-workspace/` | External reference only | Nothing in SaathiOS |

## The loop

```
  owner
    │  states a strategic objective
    ▼
  CEO Agent ─────────────► dev mission created (status: intake)
    │
    ▼
  Program Manager ───────► mission decomposed into bounded assignments
    │
    ├─► Research Agent      ──┐
    ├─► Architecture Agent  ──┤
    ├─► Security Agent      ──┼──► artifacts: findings, proposals, challenges
    ├─► Testing Agent       ──┤     (each with claims + evidence + limitations)
    └─► Cost Agent          ──┘
    │
    ▼
  meetings: Research Review → Architecture Council → Red-Team Review
    │        agenda → submissions → challenges → responses
    │        → agreements + PRESERVED disagreements → minutes
    ▼
  gates: research complete → architecture approved → security approved
    │     → implementation ready → code review → tests → red team
    │     (no agent may pass a gate on its own output)
    ▼
  CEO Agent ─────────────► executive decision, one of six terminal verdicts
    │
    ▼
  owner approval (never satisfiable by automation)
```

Only if a mission reaches an implementation handoff does a writable worktree get
created, and only for an engineering role, and only through
`saathi/engineering/`'s existing approval machinery.

## Documents

| Document | Contents |
|---|---|
| [architecture.md](architecture.md) | Discovery map, gap analysis, ADR-012, reuse and duplication rules |
| [agent-registry.md](agent-registry.md) | The 14 roles and their contracts |
| [authority-model.md](authority-model.md) | Capabilities, prohibitions, escalation, the four enforcement tiers |
| [worktree-isolation.md](worktree-isolation.md) | Branch convention, collision rules, refusal conditions |
| [mission-lifecycle.md](mission-lifecycle.md) | States, transitions, gates |
| [meeting-protocol.md](meeting-protocol.md) | Meeting types, disagreement structure, `INSUFFICIENT_EVIDENCE` |
| [review-and-evidence.md](review-and-evidence.md) | Finding requirements, no-self-approval, artifact schema |
| [behavior-evaluations.md](behavior-evaluations.md) | Offline behaviour scenarios and what they can and cannot prove |
| [operator-guide.md](operator-guide.md) | CLI usage |
| [recovery-guide.md](recovery-guide.md) | Recovering from interrupted missions and stranded worktrees |
| [security-boundaries.md](security-boundaries.md) | What this milestone may never do |
| [limitations.md](limitations.md) | Honest statement of what is enforced versus guided |

### Added in M352–M359

| Document | Contents |
|---|---|
| [terminology.md](terminology.md) | The Owner Terminology Decision Record — twelve pinned terms, twenty-two banned phrasings |
| [operations-console.md](operations-console.md) | The read-only console, its fifteen panels and how read-only is established |
| [deterministic-runner.md](deterministic-runner.md) | The seven-phase contract, the four step actions, and the handler/envelope seam |
| [model-adapter.md](model-adapter.md) | The isolated local adapter: nine capabilities, seven structural denials |
| [model-evaluation.md](model-evaluation.md) | The published rubric, the eight scenarios and the measured result |
| [adversarial-evaluation.md](adversarial-evaluation.md) | The nine attacks and what held |
| [owner-review-console.md](owner-review-console.md) | Four owner actions and the hash-chained decision ledger |
| [certification-guide.md](certification-guide.md) | What "certified" means, and how to reproduce it |
| [operating-limits.md](operating-limits.md) | Measured concurrency, memory, disk, latency and known risks |

## Honesty rule

Throughout these documents, a control is labelled **technically enforced**,
**schema validated**, **orchestration checked**, **deterministic**,
**model evaluated**, **advisory only** or **documentation only**. Prompt text
depends on agent compliance and is only detectable by evaluation. It is never
described as enforcement.

Vocabulary is not a matter of taste here: every term above is pinned in
`saathi/agentdev/terminology.py`, and `python -m saathi.agentdev terminology
audit` fails if a banned phrasing reappears on this surface.
