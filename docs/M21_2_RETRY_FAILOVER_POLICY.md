# M21.2 — Retry and Failover Policy

**Module:** `saathi/inference/provider_decision.py`

## Retry

* Default `max_retries = 0`
* When allowed: only retryable failures; bounded attempt; deterministic backoff `min(2.0, 0.05 * 2^attempt)`
* Never retry hard policy denials, kill, invalid request, privacy, cost, auth
* Retry stops if cost ceiling would be exceeded
* No background retry worker

## Failover

Requires **all** of: request allows, caller allows, decision.fallback_permitted, taxonomy failover-eligible, capability/privacy/cloud/cost/kill/circuit/cert gates, attempt limit.

**Defaults:** no fallback, no cloud fallback.

Never failover after: unknown caller, invalid request, privacy/security/auth/cost/tool/streaming denial, kill switch, trading isolation, auth failure.

## Ranking (stable, lower score wins)

1. Policy eligibility  
2. Availability  
3. Certification  
4. Capability  
5. Privacy / local-first  
6. Cost  
7. Health evidence  
8. Circuit  
9. Stable provider_id tie-break  

No random selection. Caller `force_provider` denied.
