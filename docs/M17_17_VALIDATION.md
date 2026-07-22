# M17.17 — Validation & Completion Report

## Scope delivered

Graph‑backed missions can be scheduled and launched by trusted events; a scheduled
graph mission survives interruption and resumes safely through the existing graph +
recovery layers; graph terminal state propagates honestly into mission and occurrence
state; the mission and occurrence settle exactly once; restart reconciliation covers the
documented crash windows; approval and ownership remain consistent end to end; no live
trading capability is added.

## Files changed

- `saathi/application_harness/mission.py` — graph→mission classification;
  `resume_graph_mission`, `settle_recovered`, `reconcile_running_mission`
  (mission stays the authority).
- `saathi/application_harness/scheduler.py` — additive `graph_recovery` flag on
  `dispatch_occurrence` / `_finalize_from_mission` (default off); honest
  approval mapping; `_graph_retryable` observer; `settle_occurrence_from_mission`.
- `saathi/application_harness/scheduled_graph.py` — **new** coordinator + registered
  graph‑backed templates.
- `saathi/application_harness/run_ledger.py` — **new** read‑only
  `pipelines_for_correlation` helper (no schema change).
- `saathi/repair/critical_checks.json` — 12 new blocking `scheduled_graph.*` checks.
- `tests/test_m17_17_scheduled_graph_recovery.py` — **new** 31 deterministic tests.
- Docs: `M17_17_{ARCHITECTURE,VALIDATION,MIGRATION,OPERATIONS,RECONCILIATION_SEMANTICS}.md`
  + `Brain.md`, `Business.md`, `Writing and Speaking Style.md`,
  `docs/AUTONOMOUS_ROADMAP.md`, `docs/AUTONOMOUS_LOOP_STATE.json`,
  `docs/TECHNICAL_DEBT.md`.

## Test results

- **Focused M17.17:** 31 passed.
- **M17.13–M17.16 regression:** 160 passed.
- **New critical checks (real runner):** 12/12 blocking `scheduled_graph.*` green.
- **Full critical manifest:** green (194 checks; see run output).
- **Full suite / release gate / DB integrity / backup‑restore / security / secret scan /
  `git diff --check`:** see the milestone final report (run at commit time).

## Test coverage map (representative)

| Area | Tests |
|---|---|
| Template safety | registered graph template; register idempotent+additive; sequential template unchanged; schedule cannot supply graph def; unknown template rejected |
| Scheduled launch | one graph mission per due occurrence; repeated dispatch → no duplicate; scheduler/coordinator layering (no direct graph/recovery calls) |
| State propagation | success→completed→succeeded; approval→blocked→approval_required; stop_uncertain→blocked (fail closed); retryable defers; non‑retryable terminal |
| Recovery/resume | reuse root+branch_a, rerun only branch_b + join once; idempotent recover; original failure immutable; approval does not auto‑recover |
| Crash windows | graph terminal before mission settlement (F); mission terminal before occurrence settlement (G) |
| Concurrency/dedup | concurrent dispatch → one mission+graph; concurrent recover → one resumed graph |
| Owner safety | cross‑owner recover fails closed; health owner‑scoped |
| Control Center | approval attention + owner scope |
| Trusted event | graph mission launch + dedup; payload cannot override owner/template |
| Regression | ordinary sequential scheduled mission still works; `graph_recovery` defaults off |
| Trading boundary | integration + engine recovery modules open no trading surface |

## Determinism

All tests use injected clocks, injected deterministic runners (`_fail_on`,
`_status_on`), thread barriers for concurrency, and the bounded executor. No real sleeps,
no timing assertions — no flaky tests.
