# M15.2 Tasks (drives M10 orchestration)
- T1 config guards (target/prod-block/redaction/budget) — deps: none
- T2 finding model + severity — deps: none
- T3 isolated in-process targets — deps: M15 core
- T4 deterministic probes (20 attacks) — deps: T3
- T5 runner + corpus binding — deps: T2,T4
- T6 baseline + report + hackagent wrapper — deps: T5
- T7 report API (prod-disabled) — deps: T6
- T8 deterministic security suite + harness units — deps: T4,T6
- T9 remediation of confirmed findings + regression — deps: T8
- T10 specs/manifest/docs/validation/commit — join/gate
Strategy: critical path T3→T4→T5; parallel leaves T1/T2; T6/T7 fan out; T8/T9/T10 join.
