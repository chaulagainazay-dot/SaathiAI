# M21 Handoff from M20

## M20 closed as

```text
M20 COMPLETE WITH LIMITATIONS — PILOT PLATFORM CLOSED; LIVE LOCAL INFERENCE REMAINS ENVIRONMENT-BLOCKED
```

## Superseded by M21–M39 master program (2026-07-16)

Platform numbering and first coding choice are now governed by:

* `docs/M21_39_MASTER_PROGRAM_AUDIT.md`
* `docs/M21_39_MASTER_PROGRAM_ROADMAP.md`
* `docs/M21_39_GATE_MATRIX.md`

**Platform M21** = Runtime Consolidation and Production Configuration (this monorepo).  
**PRODUCT/IELTSAlert M21.x** = separate pielts product repo — do not mix labels.

## Do not auto-start platform M21 code

Operator must authorize the first **platform** M21 slice explicitly after program init.

## Historical options (remapped — keep for history)

### Option A — Unblock local intelligence
**Was M21.0-A:** Operator-installed ≤3B model + re-run live cert + shadow `cheap_ask` only  
**Maps to:** Environment unlock + M21/M24 evidence input (not full M21 alone)

### Option B — Operator packaging  
**Was M21.0-B:** Hardened disable drills, onboarding runbook, CI job for M20.9 suite  
**Maps to:** Preferred **platform M21.0** first implementation slice

### Option C — Revenue product slice  
**Was M21.0-C:** One product feature reusing ExecutionGateway + approvals **without** expanding agent write autonomy  
**Maps to:** **M30** and/or **PRODUCT/IELTSAlert** track — not platform runtime M21

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

Authorize **platform M21.0** (recommended for master loop) **or** continue PRODUCT/IELTSAlert out-of-band — open a milestone brief **before** coding.
