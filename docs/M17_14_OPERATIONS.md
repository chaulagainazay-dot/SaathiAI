# M17.14 Operations — Mission Scheduler & Trusted Event Triggers

## Mental model
Scheduling decides WHEN a mission is due; it does NOT change HOW a mission executes.
Every scheduled or event-triggered job becomes a normal mission run through the
MissionEngine → pipeline → governed harness execution. Approvals, ownership,
verification, and Trading Guardian all behave exactly as for a hand-run mission.

## Enabling the sweep (opt-in, default OFF)
The interval runner is DISABLED by default. To run it locally:

```
export SAATHI_MISSION_SCHEDULER_ENABLED=1
```

Then start it from code (mirrors the M17.11 monitor):

```python
from saathi.application_harness.scheduler_runner import default_runner
default_runner().start(interval_sec=60)   # no-op if the env flag is not set
```

One tick = one deterministic `MissionScheduler.sweep()`:
reconcile stale leases → generate due occurrences → dispatch through the
MissionEngine. Overlapping ticks are skipped; a tick exception never fakes success.
No OS launch agent / cron / cloud scheduler is created — provisioning is out of
scope for this milestone.

## CLI (verified local OS operator; every mutation audited via the event bus)
Always available (aggregate census, no secrets):
```
python -m saathi.application_harness.cli scheduler-health
```
Admin-gated (`SAATHI_HARNESS_ADMIN=1`), owner-safe output:
```
schedules                                   # recent schedules
schedule-inspect <schedule_id>
schedule-create <owner> <template> <type> <expr_json> [params_json]
schedule-pause|schedule-resume|schedule-disable <schedule_id>
occurrences                                 # recent occurrences
occurrence-inspect <occurrence_id>
occurrence-reconcile                        # settle stale-lease occurrences
triggers                                    # trusted event subscriptions
trigger-inspect <trigger_id>
```
`schedule-create` uses a REGISTERED mission template and strictly-typed validated
parameters; `expr_json` examples: `{"run_at":1737000000}` (one_time),
`{"interval_sec":3600}` (interval), `{"time":"06:00"}` (daily),
`{"weekday":0,"time":"06:00"}` (weekly).

## Reading Control Center
The owner-safe scheduler cell exposes active/paused schedules, due/pending/claimed/
retry-wait/failed/approval-required occurrences, stale leases, and recent trigger
receipts. Attention items (owner-scoped): invalid schedule, terminal occurrence
failure, approval-required scheduled mission, stale occurrence lease, and event
trigger rejections above threshold. No raw payloads, secrets, commands, or
cross-owner data are ever shown.

## Schedule types & timezone
`one_time`, `interval`, `daily`, `weekly`. Times are UTC internally; `daily`/`weekly`
wall-clock times are computed in the schedule's IANA timezone. DST is handled by
`zoneinfo`: a daily 06:00 job stays at 06:00 local across a DST change (its UTC epoch
shifts by the offset). Ambiguous/nonexistent DST wall-clock times resolve via the
library's deterministic fold rule.

## Recurrence semantics
Each due time creates exactly ONE occurrence; each occurrence creates at most ONE
mission (deterministic id). A crash mid-dispatch is reconciled to the existing
mission — never a duplicate. A `completed` one_time schedule never runs again.

## Trusted event triggers
Register a subscription binding one allowlisted event type + template + static params
(+ optional allowlisted scalar payload→param mapping). Only
`TRUSTED_EVENT_TYPES` are accepted; a repeated `source_event_id` is deduplicated by a
durable receipt; owner/approval/risk can never be set from a payload. Ingest is a
trusted INTERNAL call (there is no public webhook).

## Retry & failure
Infrastructure failures (db lock, interrupted claim, dispatch bookkeeping) retry on a
bounded deterministic schedule `[0,60,300,900,3600]`s → terminal failure. Approval,
ownership, template, parameter, verification, and mission-outcome failures are NOT
retried — they land on the matching terminal occurrence state.

## Safety invariants (do not weaken)
No shell/adapter/pipeline shortcut; no approval elevation; no owner substitution; no
cross-owner inspection; no duplicate occurrence/mission; no arbitrary event type or
payload mapping; no raw payload display; no active-lease stealing; no disabled/paused
schedule execution; no terminal-occurrence mutation. Trading Guardian stays disabled;
scheduling never grants execution authority.
