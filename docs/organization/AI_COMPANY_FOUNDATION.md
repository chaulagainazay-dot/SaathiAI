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
