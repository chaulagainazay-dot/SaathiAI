# INTEGRATION_REHEARSAL (optional Phase 8)

**Mode:** local-only temporary branch `_rehearsal/m17-onto-canonical-baseline`  
**Base:** `e1738d7deec5f44600fbf0d99e2b8f74a4bc83d0` (recommended canonical)  
**Attempt:** cherry-pick `4197c9b` (fix) + `5f7ad09` (tests)  
**Pushed:** **no**  
**Original branches modified:** **no**  
**Rehearsal branch after cleanup:** deleted

## Result

| Item | Outcome |
| --- | --- |
| Conflicts | **none** |
| Duplicate commits | none observed |
| Files changed by fix | `saathi/application_harness/mission.py`, `scheduled_graph.py`, `scheduler.py` |
| Files added by tests | `scripts/m17_scheduled_graph_concurrency_stress.py` + test module(s) |
| Architecture contradictions | none during cherry-pick |
| Estimated repair scope | **zero** for apply; test execution still required on integration mission |
| pytest in audit env | system python lacked pytest — focused tests **not** executed in rehearsal |

## Cherry-pick log

```
[rehearsal 7f3b9b0] fix(scheduler): make concurrent graph recovery idempotent
 3 files changed, 166 insertions(+), 27 deletions(-)
[rehearsal ce3219b] test(scheduler): add deterministic recovery race coverage
 2 files changed, 419 insertions(+)
 create mode 100755 scripts/m17_scheduled_graph_concurrency_stress.py
```

## Interpretation

Phase 1 of `PROPOSED_INTEGRATION_SEQUENCE.md` is **low-risk**: M17 applies cleanly onto Candidate A without touching harness packages.
