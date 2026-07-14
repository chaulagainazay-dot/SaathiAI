# M17.17 — Operations & Runbook

## Mental model

Scheduling decides **when** a mission is due. The MissionEngine and the governed
pipeline still decide **how** it runs. A scheduled graph mission is one occurrence → one
mission → one bounded graph. If it is interrupted, the recovery coordinator reconciles
the **existing** records instead of creating duplicate work.

## Daily driving

```python
from saathi.application_harness.scheduled_graph import default_coordinator
coord = default_coordinator()

# one deterministic sweep: reconcile → generate due occurrences → dispatch (graph-recovery on)
coord.sweep(now=<clock>)

# a bounded reconciliation pass (opt-in; safe to run repeatedly)
coord.reconcile(now=<clock>)

# owner-safe Control Center aggregate
coord.health("<owner>")
```

Fresh execution flows only through `MissionEngine.launch`; recovery only through
`engine.resume_graph_mission` (→ existing graph recovery interface). Never call the graph
executor or the recovery layer directly to "force" a scheduled mission.

## Control Center view

`coord.health(owner)` returns owner‑scoped counts (graphs, recovery, occurrences,
missions) plus **attention** items — never raw commands, payloads, artifacts, secrets,
private parameters, or cross‑owner records. Attention triggers include:

- `approval_required_scheduled_graph` — a scheduled graph branch needs approval; the join
  and mission are blocked. **Action:** approve out of band (never auto‑approved).
- `stop_uncertain_graph` — a verification‑uncertain graph failed closed. **Action:**
  investigate; do not assume success.
- `retry_exhausted` — transient retries exhausted. **Action:** inspect the failure
  category; resume manually only after the cause is understood.
- `failed_graph_branch` — a branch failed. **Action:** if transient, let reconciliation
  resume it; otherwise inspect.

## Playbooks

**A scheduled graph mission is stuck in `retry_wait`.** Expected for a transient branch
failure. Run `coord.reconcile(now=...)`; it resumes the existing graph, reuses verified
branches, reruns only the interrupted branch, runs the join once, and settles the
occurrence. Idempotent — safe to run repeatedly.

**A mission is `blocked` with `GRAPH_APPROVAL_REQUIRED`.** A branch needs approval. The
occurrence is `approval_required`. Approve the underlying step through the normal approval
path, then re‑launch a fresh mission for the next occurrence — recovery never
auto‑approves, and neither a schedule, another branch, nor a retry can approve it.

**A mission is `blocked` with `GRAPH_STOP_UNCERTAIN`.** Fail‑closed: a verification could
not be confirmed. Do not force success. Investigate the branch; the occurrence is
`blocked` and surfaced for attention.

**Crash between graph and mission settlement (window F).** `coord.reconcile` calls
`engine.reconcile_running_mission`, settling the mission from the authoritative graph
state. No duplicate branch/join runs.

**Crash between mission and occurrence settlement (window G).** `coord.reconcile` settles
the occurrence from the terminal mission via the scheduler's honest mapping.

## Safety invariants (do not weaken)

- Scheduling / parallelism / recovery never imply approval.
- Terminal missions and occurrences are immutable; recovery uses a **linked** retry
  mission, preserving the original failure as audit truth.
- Retry is allowlisted (transient only) and bounded (`[0,60,300,900,3600]s`).
- One owner across the whole chain; any mismatch fails closed.
- Trading Guardian stays unengaged — no order/withdrawal/leverage/transfer surface here.
