# M62.9R Certification Matrix

States: PASS · PASS_WITH_LIMITATION (PWL) · FAIL · BLOCKED · N/A. No PASS without evidence.

| ID | Scenario | Expected | Actual | Evidence | Status |
|----|----------|----------|--------|----------|--------|
| CD-1 | Tenant-scoped entities, immutable IDs, Decimal, tz-aware | enforced | enforced | test_m62_trading_models (19) | PASS |
| CD-2 | Prohibited env / long-only / no margin-leverage-short-derivative-borrow-withdraw | rejected | rejected in Guardian + models rejection lists | SECURITY_SCAN.md | PASS |
| CD-3 | Malformed/negative/zero/cross-tenant inputs | fail-closed | fail-closed | test_m62_5, _6, _7 (22 isolation asserts) | PASS |
| MD-1 | Deterministic fixtures + replay, event ordering, dup handling | deterministic | identical hashes | test_m62_2 (16) | PASS |
| MD-2 | Corrupted replay: hash mismatch / out-of-order / malformed | fail-closed, no false "live" | rejected | test_m62_2 corrupted-checkpoint + quality | PASS |
| RT-1 | Source provenance, claims, contradictions, thesis immutability | traceable | enforced | test_m62_3 (14) | PASS |
| RT-2 | Agent cannot self-publish thesis | denied | RESEARCH_PUBLISH owner-only | models.py roles | PASS |
| ST-1 | Immutable strategy versions, look-ahead/leakage prevention | enforced | enforced | test_m62_4 (47) | PASS |
| ST-2 | Deterministic backtest, 3 identical runs, result hash | equal | r1==r2==r3 | test_deterministic_result_hash | PASS |
| OL-1 | Full order lifecycle intent→Guardian→approval→Runtime→Gateway→tool→broker→fills→accounting | canonical only | verified | orchestration.py + api.py + test_m62_5 (46) | PASS |
| OL-2 | Accept/reject/partial/fill/cancel/dup/reused-key/insufficient-cash/halted/blocked/stale/expired-approval | deterministic outcomes | verified | test_m62_5 | PASS |
| OL-3 | Direct-service / direct-API mutation bypass | blocked | HTTP calls *_via_gateway only; require_permission | api.py 2488-2540 | PASS |
| AC-1 | Cash/reserved/available, fills↔positions↔ledger↔cash↔equity conservation | zero drift | clean | test_m62_5/_6 invariants; long-duration sim | PASS |
| AC-2 | Decimal only, no browser authority calc | enforced | no client-side math | SECURITY_SCAN.md | PASS |
| RC-1 | 7 reconciliation dimensions, INFO/WARN/ERROR/CRITICAL deterministic | deterministic | verified | test_m62_6 (22) | PASS |
| RC-2 | CRITICAL drift halts; ERROR no silent mutation | halt, no mutate | verified | test_corrupted_fill_detected_and_halts | PASS |
| RP-1 | Repair plan generated, never executed; corruption persists | no auto-repair | verified | test_repair_plan_generated_but_never_executed; SECURITY_SCAN | PASS |
| CB-1 | Breaker types + scopes; smallest scope halts; broader remains authoritative | deterministic | verified | test_m62_7 (41) | PASS |
| CB-2 | Duplicate trip idempotent; trip evidence immutable; alerts durable | idempotent | verified | test_m62_7 | PASS |
| SW-1 | On-demand + scheduled sweep, overlap prevention, immutable manifest, deterministic hash | deterministic | verified | test_m62_7 | PASS |
| AK-1 | Only human actors acknowledge; agent denied; immutable; idempotent; awareness only | enforced | is_agent_actor gate | safety/service.py:594-596 | PASS |
| RS-1 | Reset denial matrix (no-ack / missing/expired/reused/cross-tenant/modified approval / stale version / corruption / drift / threshold / unhealthy MD / broader breaker / unauthorized role / agent) | denied, halt retained | fail-closed battery | safety/service.py:654-733; test_m62_7 | PASS |
| RS-2 | Successful reset: all checks clear, approval consumed atomically, no financial mutation | before==after financial state | financial_state_modified=False | safety/service.py:735-755 | PASS |
| FI-1 | Corrupted replay injection | fail-closed, halt, no repair, restart preserves halt | verified | test_m62_2/_6 | PASS |
| FI-2 | SQLite interruption at trip/finding/halt/alert/ack/reset/approval-consume/commit | full rollback, no orphan/partial/lost halt, retry idempotent | verified | test_atomic_trip_rolls_back; test_interrupted_transaction | PASS |
| CC-1 | Concurrent dup order / cancel / trip / ack / reset; optimistic conflict | one authoritative outcome, no dup mutation | verified | test_m62_5/_7; sim dup-event idempotency | PASS |
| RR-1 | Restart persistence of accounts/cash/orders/fills/positions/ledger/recon/breaker/alerts/acks/reset/approvals/idempotency | preserved, halts remain, no reuse | verified | long-duration sim restart; test_m62_5/_7 | PASS |
| TI-1 | 3+ tenants, cross-tenant safe 404, workspace/account/order/trip/approval/evidence isolation | isolated | org_id scoping everywhere | test_m62_* isolation asserts; sim 4 tenants | PASS |
| RI-1 | Viewer no mutate; operator no owner-config; agent no trip/ack/config/reset | denied | role tiers + is_agent_actor | models.py roles; safety/service.py | PASS |
| BR-1 | 11 M62.8 routes present, role-aware, read-only authority | present | 11/11 page.jsx | frontend inventory; test_m62_8 (4) | PWL |
| BR-2 | Live browser screenshot walkthrough of all workflows | screenshots | static + component-test verified; full live drive not re-run this session | test_m62_8; TRADING_UI_AUTHORITY_MODEL.md | PWL |
| LD-1 | Long-duration ≥2000 orders / ≥6000 events / ≥12 accounts / ≥3 tenants | clean, deterministic | 2240 orders, 6720 events, 16 accts, 4 tenants, invariants clean | PERFORMANCE.json | PASS |
| PF-1 | Latency/throughput/memory stable, no unbounded growth, safeguards on | stable | p95 1.57ms, 376/s, 38.9MB RSS | PERFORMANCE.json | PASS |
| DT-1 | Replay/backtest/sim repeated → identical | identical | verified | TEST_RESULTS.md determinism | PASS |
| SC-1 | No eval/exec/socket/network/credentials/live/auto-repair executable | absent | absent | SECURITY_SCAN.md | PASS |
| SC-2 | Localhost-only binding | 127.0.0.1 | launcher binds loopback; config default 0.0.0.0 fallback | SECURITY_SCAN.md | PWL |

## Summary

- PASS: 33
- PASS_WITH_LIMITATION: 3 (browser live-walkthrough not re-driven this session; localhost binding depends on launcher env)
- FAIL / BLOCKED: 0

All safety-critical gates (authority, repair non-execution, fault injection, reset battery,
determinism, isolation, accounting conservation) are **PASS**.
