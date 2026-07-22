# M20.0 — Engineering Orchestrator Architecture Audit

**Date:** 2026-07-16  
**Repository:** SaathiAI (canonical SaathiOS)  
**Branch:** `milestone/m7-security-engine`  
**Starting HEAD:** `f4065d6` (M19.6.1)  
**Prior:** M18.2–M18.4, M19.0–M19.6 knowledge + CI honesty  

**Status:** Pre-implementation audit. No Engineering Orchestrator code existed before this milestone.

---

## 1. Intake snapshot

| Check | Result |
|-------|--------|
| Canonical root | `/Users/macbookpro/SaathiAI` |
| Branch | `milestone/m7-security-engine` |
| Sync | `0/0` with `origin/milestone/m7-security-engine` at intake |
| Unrelated dirty | Untracked OpenJarvis inference docs/tests (`saathi/inference/`, etc.) — **left untouched** |
| Handoff | `.saathi-agent-state/HANDOFF.md` — M19.6 complete; next was “do not auto-start M20 without authorization” |
| Roadmap | `docs/AUTONOMOUS_ROADMAP.md` through M19.6 |
| Active agents | Claude Code CLI present; Codex CLI **not** on PATH |
| Locks | No repository write lock held by this session |
| CI | Reliability workflow recently failing environmental/manifest issues (M19.6 repairs in flight) |

---

## 2. Existing orchestration (reuse — do not duplicate)

| System | Path | Role for M20.0 |
|--------|------|----------------|
| Mission Engine | `saathi/application_harness/mission.py` | Business missions over harness pipelines — **not** coding agents. Orchestrator may *record* correlation only; never replace. |
| Mission scheduler | `run_scheduler.py`, `scheduler.py` | Opt-in harness scheduling. **Do not** create a second scheduler for engineering tasks. |
| Run ledger | `run_ledger.py` | SQLite CAS state, heartbeats, stuck-run classify, alerts. Engineering sessions should mirror concepts; optional ledger *reference*, not a second engine. |
| Run monitor | `run_monitor.py` | Stuck-run sweep + Control Center attention. Reuse **patterns** (stall, process missing, alert classes). |
| Checkpoints | `pipeline.py` / recovery | Pipeline step checkpoints. Engineering checkpoints are **task-phase** records (JSON store), not pipeline steps. |
| ExecutionGateway | `saathi/execution/gateway.py`, `universal.py` | Sole governed tool path for many actions. Engineering agent launch stays outside unrestricted shell; no second gateway. |
| Agent runtime | `saathi/agent_runtime/` | Multi-agent product runtime (build teams). Different domain; do not fork. |
| Repair loop | `saathi/repair/loop.py` | Diagnose → classify → policy → bounded repair. Reuse secret scan, git evidence, retry classification ideas. |
| Events | `saathi/events` | Publish engineering lifecycle events optionally; no second bus. |
| Knowledge Service | `saathi/knowledge/` | Prompt context via composer/adoption; data-only, no authority. |
| Codebase memory | `saathi/codebase_memory/` | Retrieval for prompt evidence. |
| Control Center | `saathi/control_center/` | Optional status later; CLI first. |
| Trading / execution | `saathi/execution/trade.py`, browser TG | **Isolated** — engineering must never touch. |

---

## 3. Existing engineering automation

| Asset | Location | Reuse |
|-------|----------|-------|
| Roadmap + candidate scoring prose | `docs/AUTONOMOUS_ROADMAP.md` | Input to backlog + selector factors |
| Loop state | `docs/AUTONOMOUS_LOOP_STATE.json` | Reference only; handoff remains authoritative for session end |
| Handoff / session | `.saathi-agent-state/HANDOFF.md`, `SESSION_STATE.json` | **Canonical** durable handoff — orchestrator updates these, does not invent a third store |
| Git evidence | `saathi/repair/evidence.py`, `saathi/ops/identity.py` | Repo readiness + commit metadata |
| Secret scan | `saathi/repair/secrets_scan.py` | Commit/prompt/output scanning |
| Injection boundaries | `saathi/knowledge/safety.py` | Prompt builder must wrap retrieved context |
| Ops CLI style | `saathi/ops/cli.py`, repair/harness CLIs | JSON emit, exit codes, no `--unsafe` |
| Claude Code | `claude` CLI on PATH | **Selected agent adapter** for pilot |
| Codex / OpenCode | Not installed / not primary | Deferred |
| Loop-engineering skill | `.grok/skills/saathios-loop-engineering` | Methodology only — maps maker/checker to SaathiOS |

---

## 4. Existing governance

| Control | Location | Engineering mapping |
|---------|----------|---------------------|
| Approval tiers / risk | ExecutionGateway, harness risk | `approval_requirement` on backlog items; write launch > plan |
| Capabilities | `saathi/capabilities.py` | Register Engineering Orchestrator as designed/built/tested |
| Tool permissions | computer_agent policy, gateway | Adapter command allowlist; no arbitrary shell |
| Repo registration | codebase memory / knowledge registry | Readiness requires registered or allowlisted root |
| Secret handling | secrets_scan, redaction | Prompt + logs + handoff |
| Kill switches | browser/TG, env disables | Orchestrator disabled-by-default + stop policy |
| SES / external status | EXTERNAL_CAPABILITY docs | No new always-on external service |

---

## 5. Reusable components (summary)

1. Run-ledger / monitor **concepts** (session, heartbeat, stall, terminal immutability).  
2. Repair **secret scan**, **git evidence**, **bounded retries**, **no push/deploy**.  
3. Knowledge **composer + safety wrap** for bounded prompts.  
4. Existing **CLI conventions** and **handoff files**.  
5. **Claude Code** as first agent process adapter.  
6. Mission engine **lifecycle vocabulary** (draft → approved → running → terminal) as analogy only.

---

## 6. Missing components (M20.0 must add)

| Gap | Minimal delivery |
|-----|------------------|
| Engineering backlog model | Structured items + statuses + JSON store |
| Deterministic candidate selector | Score + reject reasons (no LLM-only) |
| Repository readiness checker | Structured ready/blocked/unsafe |
| Bounded prompt builder | Versioned, fingerprinted, TG rules, no secrets |
| Agent session adapter | One: Claude Code + Mock for tests/pilot |
| Engineering progress monitor | Phase/heartbeat/stall/policy signals |
| Engineering checkpoints | 10-phase records |
| Validation coordinator | Planned checks with evidence |
| Engineering retry controller | Classified recoverable vs deny |
| Stop policy | Graceful / pause / terminate / quarantine |
| Commit + push verifiers | Scope, secrets, no force/merge/deploy |
| Roadmap + handoff writers | Verdicts, next action |
| Operator CLI | `python -m saathi.engineering …` |
| Disabled-by-default settings | Env + in-process defaults |

---

## 7. Duplicate risks (explicit non-goals)

| Risk | Mitigation |
|------|------------|
| Second mission engine | Engineering Orchestrator supervises **coding** tasks; does not execute harness tools or business missions |
| Second scheduler | No cron/OS scheduler; operator or explicit `launch` only |
| Second run ledger | Session state in engineering store; may *cite* harness run ids later, not reimplement CAS SQLite |
| Second approval system | Flags + required approvals on items; human via CLI/env, not a parallel L4 stack |
| Second event bus | Optional publish to existing bus only |
| Second knowledge service | Call knowledge adoption/composer; no new index |
| Uncontrolled coding agent | Disabled by default; max 1 session; readiness gate; stop policy |

---

## 8. Integration boundaries

```text
Roadmap / backlog JSON
        │
        ▼
Engineering Orchestrator (saathi/engineering)
  ├── settings (disabled default)
  ├── selector / readiness / prompt builder
  ├── agent adapter (Claude Code | Mock)
  ├── monitor / checkpoints / validation / retry / stop
  ├── commit & push verify
  └── handoff → .saathi-agent-state/*
        │
        ├── reads → Knowledge Service, git, repair secret scan
        ├── never → ExecutionService trades, TG credentials
        └── never → MissionEngine harness execution as a side path
```

---

## 9. Security risks

| Risk | Control |
|------|---------|
| Unrestricted shell via agent | Adapter argv allowlist; cwd fixed to registered root; no free-form shell from orchestrator |
| Secret leakage in prompts/logs | Redaction + secrets_scan; env presence only |
| Prompt injection → elevated rights | Retrieved content wrapped; cannot authorize launch |
| Parallel writers | Readiness checks dirty tree / merge / other sessions |
| Merge / deploy / force-push | Hard-denied stop reasons; push verifier |
| Trading crossover | Explicit isolation module + tests |
| Silent enable | Defaults false; env cannot override a structured deny for TG/trade |

---

## 10. Proposed minimal architecture

**Package:** `saathi/engineering/`  

**Store:** JSON under configurable path (default `data/engineering/`, gitignored) — not a new SQLite ledger.  

**First pilot:** Harmless documentation-consistency item supervised end-to-end with **MockAgentAdapter** (deterministic) when launches disabled; Claude adapter present but gated.  

**Verdict targets:** `ENGINEERING ORCHESTRATOR PILOT READY` when core + tests + dry pilot pass without production writes.

---

## 11. Agent adapter selection

| Candidate | Evidence | Decision |
|-----------|----------|----------|
| Claude Code | CLI at `~/.local/bin/claude`, version available | **Primary real adapter** |
| Codex CLI | Not on PATH | Deferred |
| OpenCode | No project adapter | Deferred |
| Mock | Required for tests and disabled-by-default pilot | **Always available** |

---

## 12. Decision

Implement M20.0 as a **coordination layer only**, disabled by default, with deterministic selection, readiness, mock pilot, Claude adapter scaffold, validation/retry/stop/commit/push/handoff, and full unit tests — without replacing Mission Engine, ExecutionGateway, Knowledge Service, run ledger, or Trading Guardian.
