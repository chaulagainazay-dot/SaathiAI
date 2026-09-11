# INFORMATION_ARCHITECTURE

## Decision

**Do not replace M47.2 primary nav (12 areas / 4 groups) in this milestone.**

Rationale: large route churn without product gain; operators already know Operate / Work / Business / System.

**Do elevate `/command` as the control-plane composition surface** while Home remains the attention-first landing.

## Mapping to proposed six domains (logical, not forced route rewrite)

| Domain | Primary entry | Notes |
| --- | --- | --- |
| HOME | `/` | Attention spine retained |
| COMMAND | `/command` | **UI-NEXT-1 composition** |
| OPERATIONS | `/missions`, `/agents`, `/approvals`, `/automation` | Linked from command |
| INVESTMENTS | `/trading` (+ paper routes) | Snapshot on command |
| INTELLIGENCE | `/evidence`, `/knowledge` | Timeline + deep links |
| SYSTEM | `/monitoring`, `/settings`, security | Health panel on command |

## Avoided

- New top-level route tree rewrite
- Parallel design system
- Card explosion dashboards
