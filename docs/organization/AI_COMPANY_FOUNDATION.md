# SaathiOS AI Company — Foundation (discovery + architecture)

Branch `feature/ai-company-foundation`, started from `121f3f54`
(`milestone/m312-m319-connectivity-governance`). Worktree `~/SaathiAI-ai-company`
(isolated because `~/SaathiAI` held concurrent uncommitted finance-viewport work).

## Discovery verdicts

| Subsystem | Finding | Verdict |
|---|---|---|
| Canonical topology | Next 15 on `127.0.0.1:3100` proxies `/api/v1`, `/api/events` to `:8765` (single origin, `next.config.mjs`) | KEEP |
| Central Command (`/`, `/command`) | Attention home + hybrid command (voice, trading ops) | KEEP; Company View added beside it |
| Orbit (`/orbit`) | Radial view of fleet workers | KEEP (separate concern) |
| M10 agent runtime (`saathi/agent_runtime`) | 8 AgentDefinitions, RunState machine, tasks, delegations, `agent_run` turns; `data/agent_runtime.db` | INTEGRATE — org roles bind to its ids; state adapter reads it read-only |
| Platform mission runtime + `AgentRoleRegistry` | 12 bounded AgentTypes, `FORBIDDEN_ALL` incl. `trading_execution` | INTEGRATE — bindings + forbidden-set superset |
| `saathi/agents/*` (IELTS bus), `agent_registry.py` | Legacy / domain-specific | REJECT for org use |
| Four "mission" stores (missions.db, platform, CEO=M10 runs, agentdev) | Unrelated concepts | DEFER unification; org missions are their own bounded record |
| InvestmentCommittee v1/v2 | Rule-based; defaults fabricate opinions without context; v2 reads a non-existent `synthesis` key | ADAPT later; NOT invoked by org missions (recorded as such) |
| PortfolioConstructionEngine, PortfolioRiskEngine, TradingGuardian, platform approvals, ExecutionGateway | Deterministic canonical chain; paper-only | KEEP as authority; org reads posture/budget only |
| Duplicate risk engines (tg/risk, portfolio_risk, paper_activation) | Duplicates | DEFER (flagged) |
| `submit_order` does not call PortfolioRiskEngine; durable `/tg/paper/orders` skips Gateway | Pre-existing gaps | DEFER — flagged for a trading-integrity milestone |
| GovernedBrowser / browser_research / Evidence Service | Governed, evidence-backed; no evidence-by-id route | INTEGRATE — org adds read-only `/organization/evidence/{id}` |
| Event buses | In-memory `saathi.events.bus` → SSE `/api/events/stream` (auth-exempt); SQLite `events.db` separate | INTEGRATE in-memory bus; org events carry ids/status only |
| Health endpoints | Several hardcoded "ACTIVE" | REPLACE for Company View with real probes (`system_status.py`), UNKNOWN on failure |
| Chat/voice → mission | No path exists (`ChatEngine.send` is the hook) | DEFER (Phase M) |
| CEO goals (`ceo_os.goal`) | Real owner priorities source, currently empty | INTEGRATE (Today's Focus, honest empty state) |

## Architecture added

`saathi/organization/`
- `models.py` — AgentStatus (16 states), lifecycle transition table, AuthorityLevel,
  `FORBIDDEN_CAPABILITIES` ⊇ platform `FORBIDDEN_ALL`, CAN/CANNOT, execution authority fixed `NONE`.
- `charter.py` — declarative org: 6 departments, 7 floors, 24 offices, 109 roles,
  deterministic authority chain; bindings to real runtime ids; validator fails loudly.
- `state.py` — real-state adapter (precedence documented in module docstring).
- `dependencies.py` — connector/provider/engine availability (NOT_CONNECTED/UNAVAILABLE/UNKNOWN).
- `probes.py` — deterministic read-only work units (no LLM, no writes, no gateway).
- `missions.py` — templates (portfolio review, NEPSE swing research, systems check),
  bounded runner (1 mission), persisted steps, bus events `org.*`.
- `store.py` — `data/organization.db` (`SAATHI_ORG_DB`).
- `system_status.py` — real probes, 30 s cache, no percentages.
- `api.py` — `/api/v1/organization/*`, authenticated by the global middleware.

## Authority boundary

No organization role can declare a forbidden capability, bind the M10 `executor`,
or import execution/broker/gateway code (static AST test). Missions only read.
Committee output is a proposal with `authorizes_execution: false`.

## Truthfulness rules

- Unreadable source → UNKNOWN; missing connector → NOT CONNECTED/UNAVAILABLE with reason.
- Stale runtime records (>6 h) are flagged, not shown as live work.
- Missing data → AWAITING_EVIDENCE with the specific gap (e.g. "1 bar per instrument; swing needs ≥ 20").
- Step pacing (`SAATHI_ORG_STEP_PACING_SEC`, default 1.2 s) is presentation timing, recorded on the mission.

## Certification — SAATHIOS_AI_COMPANY_FOUNDATION_CERTIFIED_WITH_LIMITATIONS

Evidence (2026-09-19):
- Backend: `tests/test_organization_foundation.py` 44 tests + neighbouring suites (agent runtime,
  control center, trading guardian M166–M175, paper crypto pipeline, orchestration M95, platform
  agent runtime M52, connectivity governance M312–M319, paper broker M62.5) — 246 passed.
- Frontend: `lib/organization.test.js` 12 + navigation; full `npm test` 1198/1201 — the 3
  failures (`data-plane` start_local.sh, two voice tests) fail identically on the untouched base.
- Browser (isolated runtime: worktree Next on :3110 → scratch validation server :8775 serving
  `/api/v1/organization/*` + SSE from worktree code, everything else proxied to canonical :8765,
  canonical data read-only): real snapshot (109 roles, 6 honestly UNAVAILABLE, 2 paper accounts),
  missions started from the UI, live SSE-driven delegation path, agent/office/mission inspectors,
  mobile list at 375 px, idle view 0 running animations (the 90 running are the shell's
  pre-existing `floaty` star field), snapshot 30 ms / 110 KB, ~3k DOM nodes.

Limitations:
1. Not yet served on canonical :3100 — `~/SaathiAI` holds another session's uncommitted
   finance-viewport WIP on `milestone/m312-m319-connectivity-governance`; promotion needs an
   owner decision (merge + restart).
2. Browser pass used scratch fixture auth (no password entry by the agent). Real auth is proven by
   API tests (401 without session/token); a browser pass with a real owner login is outstanding.
3. Reduced motion verified by unit test + CSS rule, not by OS-level emulation.
4. Organization missions are deterministic read-only probes; no model reasoning, no chat/voice →
   mission path yet (Phase M), InvestmentCommittee v1 intentionally not invoked.

## Pre-existing findings (not fixed here)
- `/api/events/stream` was gzip-buffered by the :3100 Next proxy → browsers received no live events.
  FIXED here (`Cache-Control: no-transform`) because the Company View depends on it.
- `/api/events/stream` is auth-exempt; org events therefore carry ids/status only.
- `PaperTradingService.submit_order` does not consult PortfolioRiskEngine; durable
  `/tg/paper/orders` bypasses ExecutionGateway/TradingGuardian (paper-only, but a chain gap).
- InvestmentCommittee v2 reads a `synthesis` key v1 never returns.
- `tests/test_auth_v1.py` autouse fixture deletes the real `~/.saathi/security.db`, sessions and
  audit files on every run — do not run it against a live machine until isolated.
- Several health endpoints return hardcoded "ACTIVE".
- ESLint config has no JSX configuration (all `.jsx` files are ignored).

## Next milestone (recommended)
1. Promote this branch to canonical :3100 (owner approval), browser pass with real login.
2. Phase M: chat/voice → organization mission via `ChatEngine.send` intent + owner confirmation.
3. Bounded model reasoning for synthesis roles (≤1–2 concurrent inference jobs, Ollama local),
   evidence-cited outputs; committee v2 fix; attribute M10 runs to org roles explicitly.
4. Trading-integrity milestone for the chain gaps above.
