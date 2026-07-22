# M39.2 — Live-Test Failure-Mode Simulation

**Status:** ALL_FAULTS_FAIL_CLOSED (offline; `SIMULATED_NOT_LIVE`).
**Series:** PRE-M40 offline readiness (`docs/PRE_M40_OFFLINE_READINESS_PLAN.md`).
**Module:** `saathi/credentials/m39_2.py` (composes M39 runner + M37 transport testkit + M38 retry classifier).
**Tests:** `tests/test_m39_2_failure_simulation.py` — 22 passed.
**Evidence:** `docs/evidence/m39_2/` (deterministic; leak-clean).

## Purpose

Exercise every live-only failure mode of the M39 single-session runner **without a
live provider**, by injecting fault transports/backends through the runner's
existing `transport` / `backend` / `kill_switch` seams. Confirms the runner fails
closed, closes the SecretHandle, and classifies retryability correctly for each
fault — before any real credential is ever used.

## Fault modes (11) and expected classification

| Mode | Injection | Fails closed | Retry class |
|------|-----------|--------------|-------------|
| throttle_429 | sender status 429 | yes | RETRYABLE |
| auth_denied_401 | sender status 401 | yes | NON_RETRYABLE |
| auth_denied_403 | sender status 403 | yes | NON_RETRYABLE |
| server_error_500 | sender status 500 | yes | RETRYABLE |
| malformed_response | 200 + invalid body | yes | NON_RETRYABLE |
| network_timeout | sender raises TimeoutError | yes | RETRYABLE |
| connection_reset | sender raises ConnectionResetError | yes | RETRYABLE |
| connection_refused | sender raises ConnectionRefusedError | yes | RETRYABLE |
| dns_resolution_failure | failing resolver | yes | NON_RETRYABLE |
| secret_resolution_failure | backend.get() raises | yes | NON_RETRYABLE |
| kill_switch_tripped | tripped LiveKillSwitch | yes | NON_RETRYABLE |

Baseline (fixture, no fault) must PASS — proving the harness is not trivially
failing everything.

## Verified invariants

- `all_faults_fail_closed` — every fault yields `ok=false` with a reason.
- `all_secret_handles_closed` — SecretHandle closed in every path.
- `all_retry_classifications_match` — M38 `classify_retry` matches the intended class.
- `baseline_passes` — the non-fault fixture path succeeds.
- `no_live_network` — no path performs a live call (`live_network=false` throughout).

## Scope boundary

Multi-session partial-failure and retry aggregation are already covered by M38's
failure matrix (`m38-run-failure-matrix`) and are **not** duplicated here.

## Authority state (unchanged)

CANARY / ACTIVE / rollout / production / write = **NOT GRANTED**. Trading Guardian
**UNENGAGED**. All outputs `SIMULATED_NOT_LIVE`; no live evidence produced.

## Reproduce

```bash
python -m pytest tests/test_m39_2_failure_simulation.py -q
python -m saathi.credentials.cli m39-2-simulation-matrix
python -m saathi.credentials.cli m39-2-simulate-fault --mode throttle_429
python -m saathi.credentials.cli m39-2-emit-evidence   # deterministic
```
