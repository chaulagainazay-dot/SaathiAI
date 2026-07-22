# M15.1 Tasks (drives M10 orchestration)
- T1 authenticated API (registry/account/exec/approval/health/metrics) — deps: M15 core
- T2 credential hardening (owner/connector/scope validation, typed) — deps: none
- T3 integration funnel (Chat/Agent/CEO/Voice) — deps: T1
- T4 migration ledger + direct-call scanner — deps: none
- T5 UI on real API — deps: T1
- T6 live-local verification — deps: M15 core
- T7 failure-path + backup + observability tests — deps: T1..T4
- T8 specs/manifest/docs/validation/commit — join/gate
Strategy: critical path M15-core→T1→T3/T5; parallel leaves T2/T4/T6; T7/T8 join.
