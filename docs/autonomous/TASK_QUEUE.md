# Autonomous Task Queue

## Active

- M71 — authenticated mission-runtime API and backend-driven Mission Dashboard in the
  existing unified shell.

## Pending

- M72 — end-to-end certification, security/full regression review, architecture and
  capability documentation, and terminal verdict.

## Completed

- Repository intake/recovery audit at
  `a4cb5c4d872a3edf048d52b7cd62bf9346703613`; protected pre-existing evidence/design
  changes identified and excluded.
- M69 — authoritative mission hierarchy, acyclic task graph, lifecycle state,
  prioritization, resource-budget contracts, evidence/review gates, resumable
  checkpoints, tenant-scoped dashboard read model, and restart-safe PlatformStore
  persistence.
- M69 focused/regression certification: 4 new tests; 124 related backend tests; 180
  frontend tests; retained M64 shell browser certificate (21 hard, 12 state, 6
  responsive, 3 accessibility gates); production-code secret scan clean.
- M70 — eight bounded role agents, deterministic scheduling decisions, safe parallel
  batches, PlatformAgentRuntime-only dispatch, approval resume, confirmed-failure
  retry, pause/resume/cancel, resource stops, and interruption reconciliation without
  replay after recorded dispatch.
- M70 certification: 8 new tests; 132 related backend tests; 180 frontend tests;
  retained M64 shell browser certificate (21 hard, 12 state, 6 responsive, 3
  accessibility gates); changed production-code secret scan clean.

## Blocked

- None.

## Deferred

- Future application modules, multi-host/distributed mission scheduling, cloud
  deployment, production activation, and any live financial/trading authority.
