# M20.0 — Engineering Orchestrator Architecture

**Milestone:** M20.0 Governed Engineering Orchestrator  
**Status:** Pilot (not production)  
**Package:** `saathi/engineering/`

---

## Purpose

A **control and supervision layer** that replaces manual prompt-pasting for long-running engineering work. It does **not** implement a second coding agent framework, mission engine, scheduler, run ledger, approval system, event bus, or knowledge service.

## Lifecycle

```text
roadmap item
→ candidate evaluation (deterministic)
→ repository readiness check
→ task decomposition + bounded prompt
→ agent launch (gated, default off)
→ progress monitoring + checkpoints
→ validation plan
→ repair/retry (bounded) or stop
→ commit verification / push verification (gated)
→ roadmap + durable handoff
→ stop or continue
```

## Components

| Component | Module | Role |
|-----------|--------|------|
| Settings | `settings.py` | Disabled-by-default flags |
| Models | `models.py` | Backlog item, task, statuses, verdicts |
| Store | `store.py` | JSON backlog/sessions/checkpoints under `data/engineering/` |
| Selector | `selector.py` | Deterministic weighted scoring |
| Readiness | `readiness.py` | Repo gate before write launch |
| Prompt builder | `prompt_builder.py` | Versioned, fingerprinted prompts |
| Adapters | `adapters/` | `mock` (tests/pilot), `claude_code` (real CLI) |
| Monitor | `monitor.py` | Heartbeat, stall, policy detections |
| Validation | `validation.py` | Named allowlisted checks |
| Retry | `retry.py` | Recoverable vs deny, max 3 |
| Stop policy | `stop_policy.py` | Graceful / pause / terminate / quarantine |
| Commit/push | `commit_verify.py`, `push_verify.py` | Scope + no force/merge/deploy |
| Handoff | `handoff.py` | `.saathi-agent-state/HANDOFF.md` + `SESSION_STATE.json` |
| Security | `security.py` | Allowlists, TG isolation report |
| Orchestrator | `orchestrator.py` | Lifecycle coordinator |
| CLI | `cli.py` | `python -m saathi.engineering` |
| Pilot | `pilot.py` | Harmless docs-consistency mock pilot |

## Systems reused (not replaced)

- Mission Engine / harness run ledger / monitor — concepts only; no second CAS ledger  
- ExecutionGateway — not bypassed for tools  
- Knowledge Service / safety wrap — optional context for prompts  
- Repair secret scan / git evidence patterns  
- Existing handoff files  
- Event bus — optional history append only  

## Agent adapter

**Primary real adapter:** Claude Code (`claude` CLI), fixed argv, cwd confined, secrets stripped from child env, dry-run mode for safety.  

**Default pilot:** Mock adapter (no process spawn).

## Disable controls

```bash
# Defaults are already off. To enable pilot orchestration only:
export SAATHI_ENG_ORCH_ENABLED=1
export SAATHI_ENG_ORCH_LAUNCH=1
# Writes/commits/pushes remain off unless explicitly set.
```

Unset the env vars (or set `0`) to disable. Merge/deploy/force-push/trading flags are hard-coded false.

## CLI reference (operator runbook)

```bash
python -m saathi.engineering status
python -m saathi.engineering backlog
python -m saathi.engineering select
python -m saathi.engineering readiness
python -m saathi.engineering plan <item_id>
python -m saathi.engineering launch <item_id> [--adapter mock|claude_code]
python -m saathi.engineering monitor <session_id>
python -m saathi.engineering stop <session_id> [--force]
python -m saathi.engineering validate <item_id>
python -m saathi.engineering handoff
python -m saathi.engineering pilot
python -m saathi.engineering security
```

Forbidden flags: `--unsafe`, `--skip-approval`, `--force-push`, `--deploy`.

## Next milestone (recommended)

M20.1 — Wire Control Center read-only engineering facet; optional CI status adapter; Claude live read-only supervision with explicit operator approval; still no auto-merge/deploy.
