# M14 CEO OS — Audit (Phase 1)

**Date:** 2026-07-11 · **Branch:** `milestone/m7-security-engine` @ `bac5f9d`

Classification: reusable · consolidate · migrate · deprecated · placeholder · real-data · unverified · security-risk · product-gap.

## Existing CEO/business code

| Location | Role | Disposition |
|---|---|---|
| `saathi/bff.py` | CEO Home payload; **verified 3-action-card contract** + `dream_pct` (Repair 3) | **reuse, do not regress.** M14 CEO API is additive; the BFF contract stays exactly as tested. |
| `saathi/financial_mission_control.py` `dream_progress_pct` | canonical percentage (1.0 == 1% of target) | **reuse verbatim** — the KPI engine's percentage convention. Ratio-vs-pct regression guard kept. |
| `saathi/executive.py` | `DecisionEngine`, `forecast_linear`, `compute_execution_score`, `Recommendation` | **reuse** — CEO forecasting + execution score. |
| `saathi/executive_finance.py` | `CrossDepartmentPriorityEngine`, `DepartmentRecommendation` | reuse pattern for priority explanation. |
| `saathi/ceo_os.py` | read-only aggregator `snapshot()` (studio/mission/dream/revenue/automation) | **consolidate** — CEO OS service reuses its real-data reads; not extended in place. |
| `saathi/ceo_dashboard.py` | dashboard sections | placeholder-ish; **not extended** (would fork the model). New CEO dashboard is additive. |
| `saathi/missions/store.py` | **persisted** Missions (`Mission`, `MissionStore`) | **reuse** — Mission Control creates/reads real missions; execution via M10. |
| M10 `Orchestrator` + approval store | agent runs + approvals | **reuse** — CEO missions execute ONLY through M10; approvals through the existing path. |
| M9 `MemoryEngine` | business/decision memory | **reuse** — review conclusions + accepted recommendations with provenance. |
| M13 `studio_os` | active Studio workflows | **reuse** — read active workflows for the brief. |

## Findings

- **No canonical business-entity layer** (goals/KPIs/decisions/risks/opportunities/budgets have no durable lifecycle store) → **product gap, build**.
- **Priority is partly LLM/heuristic** (`bff.compute_priority`, `executive_finance`) → M14 adds a **deterministic, inspectable** priority engine with per-factor score explanation; LLM may only *recommend* weights.
- **No real Daily Brief** — `ceo_dashboard.send_morning_briefing` builds text from aggregates but has no verified/inferred/recommended distinction or evidence provenance → build.
- **Finance** mixes actual + estimated in a few cards → M14 keeps `actual`/`estimated`/`forecast`/`unknown` as **separate states**; never shows estimate as actual.
- No direct-provider bypass risk in these files (they read stores); CEO missions must execute through M10 (enforced).

## Plan

New package `saathi/ceo/` (`data/ceo_os.db`): models (canonical entities + state machines) · store · kpi (reuse `dream_progress_pct`, metric-source truthfulness) · priority (deterministic + explanation) · brief (real data, evidence-tagged) · decisions/risks/opportunities (lifecycle) · finance (actual/forecast separation) · project_health (evidence-backed) · agent (bounded, no self-approve) · service (portfolio summary + mission creation via M10 + memory write-back) · api · cli. CEO dashboard frontend on the new API. Chat/Voice CEO retrieval hooks.

**Honesty:** authenticated browser CEO workflows, live calendar/finance connectors, and real portfolio financial values are **unverified / env-blocked** — CEO OS shows "No verified data source" rather than fabricating, and financial values are seeded only as explicitly-labeled templates, never invented actuals.
