# Twenty milestone numbering decision

Decision: reserve `M360–M368` for the bounded Twenty CRM sequence.

## Collision audit

The current Twenty branch was created from M312–M319, so its local roadmap alone
cannot establish later availability. The audit therefore inspected local and
remote branch names, commit history, roadmap/maturity/LOOP_STATE files,
certification evidence, decision records, milestone manifests, and the newer
`milestone/m344-m351-multi-agent-development-foundation` worktree.

Findings:

- Highest completed foundation range found: `M344–M351`.
- `M352–M359` is already assigned to **Agent Operations Console and Controlled
  Provider Routing** in committed M344–M351 certification evidence.
- M352 terminology work is committed at local SHA
  `9b38d90104daa0df182cbbe9dd78b08fc28cce5a`.
- M353 work is present in that separate dirty worktree and was inspected read-only.
- No assignment or implementation for `M360–M368` was found in the inspected
  branches, planning sources, manifests, or worktrees.
- No existing milestone is renumbered.

This satisfies `ONE_MILESTONE_IDENTITY_PER_SCOPE` and
`NO_DUPLICATE_SOURCE_OF_TRUTH`. Because M352–M359 is occupied, it is not reused.
M360–M368 is the next contiguous free range.

## Reserved sequence

| Milestone | Scope |
| --- | --- |
| M360 | Offline foundation terminology, owner-review record, roadmap placement, and draft publication |
| M361A | Pre-runtime readiness verification checkpoint; does not start M361 |
| M361B | Runtime-readiness gap-resolution checkpoint; does not start M361 |
| M361 | Private runtime-host approval and preparation |
| M362 | Pinned isolated Twenty sandbox deployment |
| M363 | Read-only REST/health provider connectivity validation |
| M364 | Generated GraphQL/schema/native/custom-object validation |
| M365 | Webhook delivery, signature, replay, and observation-only validation |
| M366 | Restart, persistence, backup, restore, and removal validation |
| M367 | Resource, security, network, and tenant-isolation evaluation |
| M368 | Evidence closure and read-only integration certification |

The sequence is a reservation, not permission to start M361. M361 requires an
explicit owner decision about the runtime host. `docs/autonomous/LOOP_STATE.json`
remains unchanged because it is historical branch-specific M312–M319 state; this
side branch is not allowed to rewrite that completed trading loop or pretend the
M361 runtime program has begun.
