# RISKS_AND_OWNER_DECISIONS

## Critical risks

| ID | Risk | Severity | Mitigation |
| --- | --- | --- | --- |
| R1 | Treating GitHub MERGEABLE as integration-safe | HIGH | Use this audit matrices; never merge stack out of order without bases |
| R2 | Merging PR #21 as-is onto master | HIGH | Giant false diff; retarget base |
| R3 | Declaring m344-remote as tip and dropping harness | HIGH | Prefer Candidate A; cherry-pick m17 |
| R4 | Merging m344-remote into harness tip carelessly | MED | Only cherry-pick m17 paths |
| R5 | M17 race remains on recommended tip | MED | Phase 1 cherry-pick |
| R6 | Residual subprocess tool paths | MED | Post-integration authority scan mission |
| R7 | Multi-runtime confusion (platform vs harness vs engineering) | MED | FM-C1 freeze + future consolidation milestones |
| R8 | Dual portfolio modules | MED | T-NEXT-1 single authority |
| R9 | Multi voice audio owners | MED | V-NEXT-1 |
| R10 | Stale BUILD_STATUS / master narrative | MED | Docs mission after baseline |
| R11 | Dirty original worktree accidental commit | HIGH | Never commit from dirty m312 worktree for integration |
| R12 | Twenty or Baadar WIP mistaken for baseline | MED | KEEP_SEPARATE_EXPERIMENT |
| R13 | Live trading / provider enablement pressure | CRITICAL | Hard deny without separate certification program |
| R14 | Lowering memory gate thresholds to force FM-I6.2 live | CRITICAL | Forbidden by policy; free host memory instead |

## Owner decisions required

| ID | Decision | Options | Recommendation |
| --- | --- | --- | --- |
| D1 | Accept Candidate A as canonical baseline SHA | A / B / C / other | **A** |
| D2 | Master update strategy | Stack 2A / Tip merge 2B | **2B after Phase 1** if speed needed; **2A** if PR audit trail required |
| D3 | First product pillar after integration | A voice / B trading / C UI | **C then A** |
| D4 | Fate of PR #15 Twenty | keep separate / later integrate / abandon | keep separate |
| D5 | Fate of dirty Baadar/evaluation files | discard / separate branch / integrate later | separate branch only after review |
| D6 | Whether to tag baseline | yes/no | yes annotated tag |
| D7 | PR #21 handling | retarget / supersede with FM-I stack | retarget or supersede |
| D8 | Authorize SAATHIOS_CANONICAL_BASELINE_INTEGRATION | yes/no | only after reading this audit |

## Explicit non-decisions (defaults hold)

- Live trading remains disabled  
- Provider connectivity remains disabled  
- No credential inspection  
- No history rewrite  
- No voice/trading/UI product implementation in integration mission without new auth  
