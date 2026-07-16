# M21 Handoff from M20

## M20 closed as

```text
M20 COMPLETE WITH LIMITATIONS — PILOT PLATFORM CLOSED; LIVE LOCAL INFERENCE REMAINS ENVIRONMENT-BLOCKED
```

## Do not auto-start M21

Operator must authorize the first M21 milestone explicitly.

## Recommended first milestone (choose one)

### Option A — Unblock local intelligence
**M21.0-A:** Operator-installed ≤3B model + re-run live cert + shadow `cheap_ask` only  

### Option B — Operator packaging  
**M21.0-B:** Hardened disable drills, onboarding runbook, CI job for M20.9 suite  

### Option C — Revenue product slice  
**M21.0-C:** One product feature reusing ExecutionGateway + approvals **without** expanding agent write autonomy  

## Carry-forward assets

* `saathi.engineering` orchestrator + ledger + integrity  
* `saathi.inference` gateway path + rollout + cert suite  
* `saathi.m20_console`  
* Tests: `tests/test_m20_*.py`  

## Carry-forward bans

* No TG crossover  
* No silent chat default migration  
* No auto model download  
* No unattended write/push/merge  

## Decision required

Pick A, B, or C (or a renamed bounded alternative) and open a new milestone brief **before** coding.
