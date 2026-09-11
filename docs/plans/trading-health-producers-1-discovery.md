# TRADING-HEALTH-PRODUCERS-1 — discovery map (before any code)

Branch `feature/nepse-completion`, HEAD `71d92bd5` (recovered from repository
reality, clean, in sync). TRADING-OPS-1 verified present: 43/43 pass.

## The correction this discovery makes

TRADING-OPS-1 certified that these five domains had "no typed producer". That was
**too strong**, and the brief was right to insist on searching harder. Four of the
five already have typed state contracts; one already has a full health producer.
This milestone is therefore ADAPT work, not creation.

| Domain | Existing contract | Verdict |
|---|---|---|
| **Market data** | `market_observation/models.py` — `DataFreshness` (FRESH/STALE/FROZEN/UNKNOWN), `ObservationSource` (OFFLINE_FIXTURE / FROZEN_LOCAL_CACHE / GOVERNED_DATASET / AUTHENTICATED_LIVE_FORBIDDEN), `ExchangeStatus` | **ADAPT** |
| **Provider** | `connectors/providers/models.py` — `ProviderHealthState` (9 states), `ProviderErrorCode`; `providers/health.py` — `ProviderHealthTracker`, `compute_readiness`; `provider_contracts/models.py` — `SessionState`, `CapabilityAccess` | **ADAPT — a producer already exists** |
| **Guardian** | `service.py::posture()`; `domain.py` — `AuthorityMode` (LIVE absent), `GateStatus`; `PolicyEngine`; `KillSwitchStore` | **ADAPT** |
| **ExecutionGateway** | `saathi/execution/gateway.py::ExecutionGateway`; `connectors/platform/execution.py::_GATEWAY_OK` import guard; `domain.py::ProposalStatus` | **ADAPT** |
| **Approval** | `paper_activation/approvals.py::ActivationApprovalCenter`; `ActivationApprovalStatus` (PENDING/APPROVED/REJECTED/EXPIRED/REVOKED/CONSUMED) | **ADAPT** |

`connectors/providers/health.py` already states this milestone's Rule 2 in its own
docstring: *"A healthy provider does not imply authorized execution."* The
vocabulary to reuse was there; what was missing is the mapping into `HealthClass`
and the wiring into the ops snapshot.

## Two mutating reads found — the brief anticipated exactly this

Both must be isolated rather than silently inherited:

1. **`ActivationApprovalCenter.get()` / `.list()`** call `_expire_if_needed()`,
   which sets `status = EXPIRED`, stamps `decided_at`, and calls `freeze()`. A
   read that transitions state.
2. **`ProviderHealthTracker.get()`** calls `_rec()`, which **creates and inserts**
   a record when the provider is unknown. A read that grows the store.

Neither is a defect in those modules — lazy expiry is the approval authority
failing closed on its own clock, and `_rec` is a defaulting accessor. But a health
producer must not be the thing that triggers them. Handling is stated in the
implementation and in the certification's limitations.

## What is genuinely missing

Not state. **Mapping and wiring**: nothing turns any of these typed states into
`HealthClass` with reason codes, and nothing feeds them to `build_snapshot`. The
ops layer types the fields correctly and no caller populates them.

## Vocabulary decision

`HealthClass` (HEALTHY/WARNING/DEGRADED/CRITICAL/FAILED_SAFE) has **no UNKNOWN
member**, and inventing one would fork the canonical vocabulary this program has
twice refused to fork. So insufficient evidence is expressed as
`health_class = WARNING` plus an explicit `evidence_sufficient = False`, a
`state_code` of `INSUFFICIENT_EVIDENCE`, and a `MANUAL_OPERATOR_VALIDATION`
action. Never HEALTHY — that is `NO_DEFAULT_HEALTHY_ON_MISSING_EVIDENCE`. The
choice of WARNING over DEGRADED is recorded as a limitation: not knowing is a
monitoring gap, not a proven fault, and the operator is told to verify manually.
