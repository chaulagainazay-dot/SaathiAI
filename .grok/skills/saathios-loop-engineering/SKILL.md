---
name: saathios-loop-engineering
description: >
  SaathiOS-adapted loop-engineering methodology for autonomous development loops.
  Use when designing agent loops, scheduling verification, maker/checker splits,
  milestone gates, budget/kill switches, or mapping loop primitives onto SaathiOS
  harness, ExecutionGateway, and Trading Guardian. Adapted from
  cobusgreyling/loop-engineering (MIT); does not install upstream CLIs by default.
license: MIT (adapted principles; upstream loop-engineering is MIT)
---

# SaathiOS Loop Engineering

## Source and boundary

- **Upstream:** [cobusgreyling/loop-engineering](https://github.com/cobusgreyling/loop-engineering) (Skill / methodology; MIT).
- **SaathiOS status:** `REGISTERED` — methodology skill only in ECP foundation.
- **Does not replace:** Mission engine, run ledger, approvals, ExecutionGateway, CEO OS, or Trading Guardian.
- **Does not authorize:** unattended production deploys, live trading, or always-approve side effects.

## Core idea

Design the **system that prompts the agent** (loop), not only single prompts.

Map upstream primitives → SaathiOS:

| Loop primitive | SaathiOS mapping |
|----------------|------------------|
| Schedule | Documented cadence; no silent always-on agents on 8 GB Mac |
| Triage skill | Project skills under `.grok/skills/` + AGENTS.md |
| STATE.md | Milestone reports, `docs/AUTONOMOUS_LOOP_STATE.json`, Evidence |
| Worktree | Isolated worktrees for risky changes when needed |
| Implementer | Coding agent on a **bounded milestone** |
| Verifier | Focused tests + `python3 -m saathi.ops release-check` + full suite |
| Human gate | Approvals / ExecutionGateway / no push without explicit auth |
| Memory | Run ledger + Evidence authoritative; Continuum pilot is **engineering knowledge only** (later milestone) |

## Mandatory checklist (before unattended loops)

1. **Single goal** and explicit non-goals for this iteration.
2. **Maker/checker split** — implementer cannot self-certify “done”.
3. **Focused tests first**, then broader suite.
4. **Budget** — time, tokens, and Mac memory (8 GB); prefer `ON_DEMAND_LOCAL`.
5. **Kill switch** — stop rules: license, credentials, resource, security, TG.
6. **Denylist** — secrets, production writes, live trading, home-dir mounts.
7. **One milestone per invocation** unless user authorizes multi-milestone.
8. **Evidence** — commands + results recorded; never claim pass without running.

## SaathiOS stop results (use exactly)

`COMPLETE` · `PARTIAL` · `BLOCKED_ENVIRONMENT` · `BLOCKED_CREDENTIAL` · `BLOCKED_LICENSE` · `BLOCKED_RESOURCE` · `FAILED_VERIFICATION` · `REQUIRES_HUMAN_DECISION` · `DEFERRED`

## Anti-patterns

- Running Priority 1+2+3 installs in one session.
- Treating clone/docs/MCP stub as “integrated”.
- Letting MCP tool output become ToolIntents or shell commands without gateway policy.
- Weakening Trading Guardian for “research convenience”.

## Disable / rollback

- Skill-only disable: Grok `[skills] disabled = ["saathios-loop-engineering"]`.
- Do not `npx loop-init` into the monorepo without a dedicated milestone and license check.
