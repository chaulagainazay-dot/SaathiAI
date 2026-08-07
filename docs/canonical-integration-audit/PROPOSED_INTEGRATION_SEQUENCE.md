# PROPOSED_INTEGRATION_SEQUENCE

**Status:** proposal only — **not executed** (except optional local rehearsal recorded separately).  
**Recommended starting HEAD:** `e1738d7deec5f44600fbf0d99e2b8f74a4bc83d0` (`hardening/fm-i6.2-macos-memory-gate-fix`)

## Principles

1. Never merge solely because GitHub says MERGEABLE.  
2. Prefer **linear publish** of already-contained work over replaying commits twice.  
3. Prefer **cherry-pick bounded commits** for m17 over merging divergent m344-remote tip.  
4. Keep original branches and PRs intact until owner archives.  
5. Financial execution, live trading, provider activation remain disabled.

## Phase 0 — Declare baseline (no code merge)

| Step | Action | Disposition |
| --- | --- | --- |
| 0.1 | Owner accepts Candidate A SHA as canonical integration HEAD | OWNER_DECISION_REQUIRED |
| 0.2 | Tag annotation optional: `canonical/saathios-pre-m17` at `e1738d7deec5f44600fbf0d99e2b8f74a4bc83d0` | OWNER_DECISION_REQUIRED |
| 0.3 | Freeze new feature work onto non-baseline branches | process |

## Phase 1 — Close the only missing certified fix

| Step | Action | Disposition |
| --- | --- | --- |
| 1.1 | From baseline, create `integration/canonical-baseline-m17` | new branch |
| 1.2 | Cherry-pick `4197c9b` (fix) + test commit(s) + docs commits for M17 | **CHERRY_PICK_BOUNDED_COMMITS** |
| 1.3 | Run `tests` focused on scheduled_graph concurrency + application_harness | validate |
| 1.4 | Open draft PR base=`hardening/fm-i6.2-macos-memory-gate-fix` | publish |

**Do not** merge `origin/m344-m351` into baseline wholesale.

## Phase 2 — Publish product history to master (stack or tip)

Two owner options:

### Option 2A — Stacked PR merge (maximum auditability)

Merge open stack in order:

```text
#3 → #4 → #5 → #6 → #7 → #8 → #9 → #10 → #11
```

Then **PUBLISH_MISSING_BASE** for intermediate milestones currently only on the long chain (m54–m61, m166–m311, m304–m336, ui-recovery, e2e, private-alpha, m344, m369, m377, fm-c*, fm-i*) — either as stacked PRs or as a documented fast-forward series from already-linear commits.

### Option 2B — Authorized tip fast-forward / merge commit (faster)

After Phase 1 validation:

- Merge integration tip to `master` with a single merge commit or fast-forward if possible  
- Requires explicit owner authorization  
- Still **does not** rewrite historical milestone branches  

**Risk of 2B:** GitHub loses per-milestone PR review granularity. Mitigate with this audit's matrices as the review packet.

## Phase 3 — PR hygiene (no silent closes without owner)

| PR | Action |
| --- | --- |
| #21 | **RETARGET_PR** base from `master` to true predecessor (e.g. fm-c2 / pre-I6 commit) or split FM-I1–I6 |
| #14 | **RETARGET_PR** base to actual parent near full-e2e (m336 or private-alpha ancestor) |
| #15 | **KEEP_SEPARATE_EXPERIMENT** |
| #3–#13, #18–#20, #22 | **MERGE_AS_IS** when their base is already on target line |
| #16, #17 | **ARCHIVE_AFTER_INTEGRATION** (merged); ensure #17 content on baseline via Phase 1 |
| #1, #2 | already archived on master |

## Phase 4 — Explicit non-integration

| Item | Disposition |
| --- | --- |
| Dirty Baadar/evaluation WIP on original worktree | **KEEP_SEPARATE_EXPERIMENT** / do not auto-commit |
| Twenty CRM | **KEEP_SEPARATE_EXPERIMENT** |
| Live providers / broker | **REJECT** activation |
| Voice streaming redesign | not in integration sequence |
| Hedge-fund live path | not in integration sequence |

## Rollback strategy

1. **Pre-integration tag** on Candidate A.  
2. Phase 1 lives on side branch until green.  
3. If master receives tip merge and fails CI: `git revert -m 1 <merge>` (no force-push).  
4. Milestone branches remain recoverable forever.  
5. Worktrees of historical tips left intact.  
6. Evidence directories never deleted.

## Dependency-aware numbered sequence (execution checklist)

1. Owner accepts Candidate A.  
2. Branch from A; cherry-pick M17; test; draft PR.  
3. Owner merges M17 integration PR to A (or successor integration branch).  
4. Retarget misleading PRs (#21, #14).  
5. Owner chooses Option 2A or 2B to move `master`.  
6. After master catches tip: archive draft stack PRs as integrated.  
7. Only then authorize product pillar missions (prefer Pillar C composition or Pillar A bounded voice — see gap matrix).  

**Stop:** Do not execute this sequence in the audit mission.
