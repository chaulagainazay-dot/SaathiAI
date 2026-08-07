# CONVERGENCE_BASELINE_DECISION — UI-NEXT-3

## Selected approach

```text
A. Convergence branch with bounded merges
```

## Selected base

| Field | Value |
| --- | --- |
| Base branch | `feature/t-next-3-portfolio-construction` |
| Base SHA | `5fed77ac05207967aee472a6b616550a02aa0070` |
| Merge in | `test/ui-next-2-2-hybrid-browser-certification` @ `dc52c0b97a298eb228359c518c2de5b2e21de1e5` |
| Merge-base (UI vs T) | `d66fa3aea03dbb8f5daed431ff62d64fad7906a9` (UI-NEXT-1 tip) |
| Work branch | `feature/ui-next-3-production-hybrid-command` |
| Worktree | `~/SaathiAI-ui-next-3` |

## Why this is safest

1. **Zero path conflicts** between T-NEXT-3-only and UI-NEXT-2.2-only trees relative to merge-base (`comm -12` empty).
2. **Trading authority first**: production Command must read canonical ledger (T-NEXT-1/1.1), risk (T-NEXT-2), and proposal contracts (T-NEXT-3). Starting from T-NEXT-3 preserves those contracts and `command-composition` risk pass-through.
3. **UI is presentation**: Hybrid design-lab (UI-NEXT-2.1/2.2) is a clean add under `saathi-os/app/design-lab` + `lib/design-lab/*` without rewriting production authority.
4. **Bounded merge only**: one explicit merge of certified UI tip; no casual whole-history stack of unrelated branches.
5. **Does not merge** open PR stacks into `master`; Draft PR only.

## Included PR / branch chains

| Chain | Branch / PR | Included |
| --- | --- | --- |
| UI-NEXT-1 | `feature/ui-next-1-central-command` | via merge-base |
| UI-NEXT-2 | `design/ui-next-2-saathios-design-dna` | via UI-NEXT-2.2 ancestry |
| UI-NEXT-2.1 | `feature/ui-next-2-1-hybrid-command-prototype` | yes (through #40) |
| UI-NEXT-2.2 | PR #40 `dc52c0b` | yes (merged) |
| T-NEXT-1 | `feature/t-next-1-canonical-paper-ledger` | yes (T3 ancestry) |
| T-NEXT-1.1 | `feature/t-next-1-1-paper-ledger-cutover` | yes |
| T-NEXT-2 | PR #37 | yes |
| T-NEXT-3 | PR #41 `5fed77a` | **base** |

## Excluded

| Item | Reason |
| --- | --- |
| Voice PR #34 / 2B.6 product speech | Separate product track; not required for Command production shell |
| Auto-merge of #35, #36, #37, #40, #41 into master | Forbidden by mission |
| Full master integration | Out of scope |

## Conflict analysis

| Area | Result |
| --- | --- |
| `saathi/platform/*` trading | T3 only |
| `saathi-os/lib/command-composition.js` | T3 only (UI2.2 did not touch) |
| `saathi-os/app/design-lab/*` | UI2.2 only |
| `saathi-os/app/command/page.jsx` | Unchanged between tips (UI-NEXT-1 composition) |
| Merge conflicts | **None** |

## Authority impact

| Boundary | Impact |
| --- | --- |
| Fund ledger | Unchanged; UI reads only |
| Risk engine | Unchanged; UI reads only |
| Portfolio construction | Unchanged; proposals are proposals only |
| Trading Guardian | No weaken |
| ExecutionGateway | No bypass |
| Design-lab DEMO fixtures | Remain **fixture-only**; production `/command` must not default to DEMO |

## Rejected alternatives

| Option | Why not |
| --- | --- |
| B. Cherry-pick UI onto trading | More error-prone than clean merge with zero conflicts |
| C. Cherry-pick trading onto UI | Risk of missing ledger/risk/construction commits |
| D. New branch from merge-base only | Would require replaying both chains; merge achieves same with less risk |

## Decision lock

```text
BASE = T-NEXT-3 @ 5fed77a
MERGE = UI-NEXT-2.2 @ dc52c0b
THEN = promote Hybrid architecture to production /command with LIVE/UNAVAILABLE provenance
```
