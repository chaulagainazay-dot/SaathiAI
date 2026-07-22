# M15.3 Tasks (drives M10 orchestration)
- T1 scope engine — deps: M15
- T2 oauth lifecycle SM — deps: none
- T3 resilience (circuit+rate) — deps: none
- T4 error taxonomy — deps: none
- T5 live-validation framework — deps: M15
- T6 engine wiring (scope+circuit, ownership intact) — deps: T1,T3
- T7 red-team expansion + tests — deps: T1..T6
- T8 manifest/docs/runbook/specs/validation/commit — join
Strategy: parallel leaves T2/T3/T4; path T1→T6; T5/T7 fan out; T8 join.
