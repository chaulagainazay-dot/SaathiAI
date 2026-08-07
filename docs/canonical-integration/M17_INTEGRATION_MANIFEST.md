# M17_INTEGRATION_MANIFEST

**Integration branch:** `integration/saathios-canonical-baseline`  
**Source baseline:** `hardening/fm-i6.2-macos-memory-gate-fix` @ `e1738d7deec5f44600fbf0d99e2b8f74a4bc83d0`  
**Date:** 2026-08-07

## Selection rule

Do **not** merge `origin/milestone/m344-m351-multi-agent-development-foundation`.  
Only bounded M17 commits from `fix/m17-scheduled-graph-concurrency` were considered.

## Source commits (original SHAs on fix branch)

| Original SHA | Purpose | Type | Safe cherry-pick? | Decision |
| --- | --- | --- | --- | --- |
| `4197c9b6d4ba22af6c34426f5efb7a9892cf1892` | make concurrent graph recovery idempotent | implementation | YES | **PICKED** |
| `5f7ad09adc8f02ca88df57e38600c29819ee7f26` | deterministic recovery race coverage + stress script | tests | YES | **PICKED** |
| `5e3d312a77310ccd039ad39fcaee5a796ab4e818` | original M17 certification evidence pack | historical docs | YES (immutable provenance) | **PICKED** |
| `36d66e90a5862d1a6066159e7bb154da906b1847` | pin final cert SHA (historical) | docs | YES | **PICKED** |
| `d543b2c86de9a330560ce4ed04fb06b05556ff8f` | align cert final_sha (historical) | docs | YES | **PICKED** |
| `8577f2fbf10ea9d7a631ba9be861e574155bab7b` | record green GitHub CI (historical) | docs | YES | **PICKED** |

## Rejected

| Item | Reason |
| --- | --- |
| Merge commit PR #16 on m344-remote | not M17; already ancestral content via m369 |
| Merge commit PR #17 | merge wrapper only; content covered by cherry-picks |
| Whole `m344-remote` tip | would omit harness / create reverse integration risk |

## Files changed (implementation)

- `saathi/application_harness/mission.py` — concurrent recover idempotency / single resumed graph
- `saathi/application_harness/scheduled_graph.py` — recovery coordination
- `saathi/application_harness/scheduler.py` — dispatch/recovery boundaries

## Files added (tests)

- `tests/test_m17_17_scheduled_graph_recovery.py` — extended race/concurrency coverage
- `scripts/m17_scheduled_graph_concurrency_stress.py` — certification stress harness

## Dependencies

- Existing M17.17 scheduled graph recovery machinery on baseline
- No ExecutionGateway API change
- No Trading Guardian change
- No agent_runtime harness change

## Cherry-pick result on this branch

Zero conflicts. New SHAs (post-pick):

- `4b65d0428feaf5e18cb71b4c0bf097884adc180d` — fix(scheduler): make concurrent graph recovery idempotent
- `655dd928e9252272b0ed8282e1371798f7c208ce` — test(scheduler): add deterministic recovery race coverage
- `13bf79ece6c3423880c7b673d987b59213c3c0fb` — docs(scheduler): certify M17 concurrency recovery repair
- `fc0f04ff44b2670248c53c0ee6a491d382cbf847` — docs(scheduler): pin final certification SHA for M17 concurrency repair
- `6a33adab6e98fa6d2e18463856f5698b443765db` — docs(scheduler): align certification final_sha with tip
- `272dbd5d0b9495d9682955074a76b4931e440daf` — docs(scheduler): record green GitHub CI for M17 concurrency repair
