# M16 Tasks (drives M10 orchestration)
- T1 bounded aggregator (guarded cells, partial failure, freshness) — deps: M8-M15.3
- T2 read models (overview/attention/health/security/release/timeline) — deps: T1
- T3 federated search (owner-scoped, secret-free) — deps: M15
- T4 action descriptors (canonical-API pointers) — deps: none
- T5 read-only API + CLI — deps: T2,T3,T4
- T6 Overview UI on real API — deps: T5
- T7 tests (unit/isolation/read-only/auth/UI) — deps: T1..T6
- T8 manifest/specs/docs/validation/commit — join
Strategy: path T1→T2→T5→T6; parallel leaves T3/T4; T7/T8 join.
