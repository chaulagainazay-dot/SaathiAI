# M47.8 — GitHub Readiness

**PR:** #2  
**Head at review start:** `7dfd74de00241ae0fb05f99f36b3909ff16f9120`

## Mergeability

| Field | Value |
|---|---|
| `mergeable` | **MERGEABLE** |
| `mergeStateStatus` | UNSTABLE while checks in progress; no conflict |
| `reviewDecision` | empty (no required approving review submitted) |
| Conflicts | **none** |

## Status checks

| Check | Workflow | Classification |
|---|---|---|
| `critical-regressions` | reliability | **PENDING** at first poll (~14–20 min expected for critical path); must not be **FAILING** for draft exit |

Workflow design notes (`.github/workflows/reliability.yml`):

- Critical path ~18–20 min historically; job timeout 40 min  
- Full suite may run separately; PR branch concurrency cancels superseded runs  
- CI is diagnose-only — never deploys  

## Local equivalents (documented PASS)

| Gate | Local result |
|---|---|
| Frontend unit tests | 64 pass |
| CORS unit tests | 13 pass |
| Lint | pass |
| Build | pass |
| M47.7 browser cert | `M47_7_COMPLETE_WITH_LIMITATIONS` all hard gates true |
| Secret scan (PR files) | no hits |

## Draft-exit policy applied

- No merge conflict → OK  
- No failing required check → required before `gh pr ready`  
- Pending critical-regressions: **wait for completion** on final pushed SHA  
- Optional missing checks: N/A  

## Final classification (filled at close)

See `M47_8_FINAL_REPORT.md` for post-push check outcome.
