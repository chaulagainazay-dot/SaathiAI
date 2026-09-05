# FM-I1.5 — Harness Verification, Fuzzing, and Stress Certification

**Status:** Internal non-production stress certification  
**Date:** 2026-08-07  
**Authorized baseline:** FM-I1 @ `bf957f8fd7c942bcc139a30dfcb596c9d6b44fec`  
**Branch:** `implementation/fm-i1.5-harness-stress-certification`  
**Production certified:** **False**

---

## Scope

Stress-test and harden the FM-I1 FakeInMemoryHarness + HarnessSessionController
**before** any real model, provider, process, filesystem, browser, or network adapter.

| In scope | Out of scope |
| --- | --- |
| Property tests for state machine | Real ExecutionGateway (FM-I2) |
| Event-protocol fuzz quarantine | Durable persistence (FM-I3) |
| Concurrent session isolation | LocalModelHarness (FM-I5+) |
| Fault injection | Commercial CLIs |
| Deterministic replay | Providers / credentials |
| Pre-declared performance thresholds | Production activation |
| Targeted coverage of harness package | FM-I2+ work |

## Hardening applied (defects found under stress)

1. **Sequence gaps fail closed** — controller quarantines gaps (no silent accept).
2. **Full-stream ingest** — regression and duplicate event IDs are detected even when
   `seq <= watermark` would be skipped by `after_seq` polling.
3. **Stream-level duplicate event_id detection** — second append with same id quarantines.
4. **Forged run_id / mission_id** — event scope checks extended.
5. **Secret-shaped payload keys** — fail-closed quarantine with whole-key match
   (avoids false positive on `fake_tokens`).
6. **Private CoT keys** — quarantine (not only strip) on controller normalize path.
7. **Post-terminal active events** — quarantine late TURN/TEXT/TOOL events.
8. **submit_turn only from READY** — no parallel turns while WAITING_FOR_TOOL.
9. **Controller RLock** — concurrent start/turn/cancel/poll safety.
10. **Gateway / audit fault injection** — fail-closed deny / quarantine paths.
11. **Deterministic clock/id hooks** — replay certification.
12. **force_timeout / purge_closed_sessions** — timeout coverage + memory cleanup.

## Pre-declared thresholds (`harness/thresholds.py`)

| Metric | Threshold |
| --- | --- |
| Session start | ≤ 50 ms |
| Turn processing | ≤ 50 ms |
| Cancel latency | ≤ 50 ms |
| Event throughput | ≥ 200 events/s |
| Memory growth (50 sessions) | ≤ 64 MiB (tracemalloc) |
| Resident closed sessions after purge | 0 |
| Concurrency levels | 10, 50, 100 |

## Tests

| Suite | Role |
| --- | --- |
| `tests/test_fm_i1_agent_harness.py` | FM-I1 regression (36) |
| `tests/test_fm_i1_5_harness_stress.py` | FM-I1.5 stress/fuzz/concurrency |

## Explicit non-actions

No real adapter · no provider · no credentials · no network/process/browser ·
no AgentSessionAdapter changes · no ExecutionGateway replacement · no FM-I2.

## Freeze disposition

| Freeze | Disposition |
| --- | --- |
| FZ-01 | Remains partially unfrozen for internal fake proof only |
| FZ-02 / FZ-07 | Fully retained |
