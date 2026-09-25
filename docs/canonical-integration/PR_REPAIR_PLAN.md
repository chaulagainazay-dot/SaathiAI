# PR_REPAIR_PLAN

**Rule:** Prefer documentation over destructive retargets unless clearly safe.  
**No PRs closed or merged by this mission.**

## After canonical baseline exists

Canonical integration PR (this branch) should base on:

```text
hardening/fm-i6.2-macos-memory-gate-fix
```

(docs + M17 only — not a giant master diff).

## Active PR recommendations

| PR | Title (short) | Recommendation | Notes |
| --- | --- | --- | --- |
| #3–#11 | M48–M53 stack | **KEEP_AS_HISTORICAL_DRAFT** until master publish strategy chosen | Still valid stack onto master |
| #12–#13 | M312 / M320 | **KEEP_AS_HISTORICAL_DRAFT** | Contained in baseline ancestry |
| #14 | Full E2E recovery | **RETARGET** base toward true parent near full-e2e **or KEEP_AS_HISTORICAL_DRAFT** | Stale base m320; content already ancestral to baseline |
| #15 | Twenty CRM | **KEEP_AS_HISTORICAL_DRAFT** / separate experiment | Not in baseline |
| #16–#17 | Merged | Historical | #17 content now on canonical via cherry-pick |
| #18–#20 | Harness design stack | **KEEP_AS_HISTORICAL_DRAFT** | Ancestral to baseline |
| #21 | FM-I6 on master | **RETARGET** or **SUPERSEDE** | Giant false diff vs master; head already in baseline ancestry |
| #22 | FM-I6.2 memory gate | **KEEP_AS_HISTORICAL_DRAFT** | Head is Candidate A source tip |
| #23 | Audit | **KEEP_AS_HISTORICAL_DRAFT** | Analysis only; remains valuable |
| **New** | Integrate canonical baseline | **Draft PR this mission** | M17 + integration docs |

## Owner decision

Master catch-up (stack merge vs tip publish) remains **OWNER_DECISION_REQUIRED** and is **out of scope** for this mission.
