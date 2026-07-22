# M17.9 Readiness Audit — Durable Run Ledger, Concurrency Safety & Recovery Ops

Detected state at selection: branch `milestone/m7-security-engine`, HEAD `2dcfd3d`
(M17.8 governed long-running task control). Full suite 1,509 passed / 1 skipped.

## Priority scan (no higher Critical/High open)
- `critical_checks` green; red-team held; server import + route count pass.
- Release blockers remain environment-blocked (authenticated browser, live
  approval click, staging deploy+rollback) — need credentials/deploy, not code.
- Therefore the highest-value ready-now gap is durability + concurrency safety of
  the M17.8 run-tracking layer, which is the explicit top real-debt item.

## The gap M17.8 left (evidence)
From `docs/M17_8_VALIDATION.md` "Known limitations":
- run journal is append-only JSONL, **single-process** (lock-serialized), not a
  multi-writer store;
- multi-user concurrency proven only by cross-user gate tests, **not at scale**;
- no pause/resume/checkpoint;
- **no M17.8-specific blocking Critical Manifest entry**;
- no operational alerting for stuck/abandoned runs.

Concretely, `run_journal.py` appends `{run_id,event,state,...}` lines and folds
them at read time. There is no transactional state machine: nothing prevents a
second writer from recording a conflicting terminal record, nothing enforces
one-claimant-per-run, and a terminal run could in principle be "resurrected" by a
late append. Recovery (`reconcile`) is best-effort over a text log. This is
acceptable for one process; it is not safe for concurrent processes or for
exactly-once terminal-state guarantees.

## Candidate scoring (this invocation)
| candidate | priority | ready-now | notes |
|-----------|----------|-----------|-------|
| **M17.9 durable run ledger + concurrency + recovery ops** | #1 | 5 | closes the top real-debt item; transactional SQLite ledger, one-claimant CAS, terminal immutability, ownership-safe cancel, exactly-once crash recovery, multi-process proofs; reuses the ONE adapter (no second engine); no install/credential |
| production monitoring/alerting dashboard | #3 | 3 | valuable but larger/less bounded; partially unblocked by this ledger's read model |
| authenticated browser workflow | #4 | 1 | needs a safe staging credential (blocked) |
| general pause/resume/checkpoint | — | 2 | application checkpointing is unsafe to claim; only POSIX SIGSTOP/SIGCONT is real, and is deferred as contract-only here |
| native Finder/TextEdit actuation | — | 0 | macOS TCC permission required (blocked) |

## Decision
Select **M17.9**. It is the highest-value, fully-local, fully-validatable upgrade
of an already-built layer, and it directly removes the M17.8 limitation list
(single-writer journal, unproven concurrency, missing blocking manifest entry).

## Truthful scope boundaries (documented, not pretended)
- Transactional **run state** is not exactly-once **external** side effects — an
  uncertain outcome is recorded as `stop_uncertain`, never blindly retried.
- Process **suspension** (SIGSTOP/SIGCONT) is not application **checkpointing**;
  this milestone keeps pause/resume as a `contract_ready` capability contract and
  does not pretend checkpointing exists.
- Recovery never reruns a non-idempotent operation and never overwrites a live
  process.

## Verdict entering development
NOT READY → target **RUN LEDGER DEVELOPMENT/STAGING READY** for this invocation
(single-node, local multi-process proven). Production-ready is explicitly out of
scope (needs multi-user load evidence, production monitoring/alerting, a
representative deployment, and an incident-response drill).
