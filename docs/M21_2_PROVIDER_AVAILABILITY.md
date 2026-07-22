# M21.2 — Provider Availability Model

**Module:** `saathi/inference/availability.py`  
**Descriptor:** `saathi/inference/provider_descriptor.py`

## States

```text
KILLED > DISABLED > MISCONFIGURED > CIRCUIT_OPEN > UNCERTIFIED
> UNAVAILABLE > FAKE > TEST_ONLY > DEGRADED > AVAILABLE > UNKNOWN
```

## Readiness axes (non-interchangeable)

* configured
* enabled
* reachable
* healthy
* capability_compatible
* policy_eligible
* production_certified (provider flag; global production_certified remains false)

## Decision fields

* state, reason_code, redacted explanation
* evidence_tier (none | policy | config | injected | probe | live)
* checked_at
* retry_allowed / failover_allowed

## Health

Live network probes are **injectable**. Unit tests use fakes. Default probe returns unknown health → DEGRADED in pilot, UNKNOWN (not AVAILABLE) in production posture.
