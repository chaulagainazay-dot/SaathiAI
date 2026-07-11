# M17 Tasks (drives M10 orchestration)
- T1 perception model (UIElement/Screen) — deps: none
- T2 provider abstraction (deterministic + honest env-blocked live) — deps: T1
- T3 operations as connectors (risk-classed, verify flag) — deps: T2,M15
- T4 replay (sanitized) — deps: none
- T5 agent runner (gateway funnel) — deps: T3,T4
- T6 red-team probes + Computer Center — deps: T5
- T7 tests/manifest/specs/docs/validation/commit — join
Strategy: path T1→T2→T3→T5; parallel leaf T4; T6/T7 join.
