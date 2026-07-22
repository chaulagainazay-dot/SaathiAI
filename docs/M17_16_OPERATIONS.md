# M17.16 — Operations & Runbook

## CLI surface (`python -m saathi.application_harness.cli ...`)

Always-safe (aggregate census, no owner or secret data):

* `pipeline-graph-health` — graph-pipeline state census + branch/claim summary.

Admin-gated (`SAATHI_HARNESS_ADMIN=1`; the audited operator is the trusted local
OS identity — never caller-supplied):

* `pipeline-graph <pipeline_id>` — owner-safe graph structure + dependencies +
  branches + run state + steps.
* `pipeline-branches <pipeline_id>` — per-branch states.
* `pipeline-branch-inspect <pipeline_id> <branch_key>` — one branch.
* `pipeline-graph-history` — recent graph pipelines.
* `pipeline-graph-reconcile` — settle stale per-step claims (expired leases only).
* `pipeline-graph-resume <pipeline_id>` — audited resume of a FAILED graph,
  driven **through the owning mission template** (no arbitrary graph specs).

The CLI never exposes raw commands, argv, artifact contents, secrets, or approval
material. There is no force-success, no force-valid-checkpoint, no arbitrary step
skipping, no direct adapter execution, and no approval bypass.

## Control Center

The owner-safe harness cell now includes `graph_pipelines`, `graph_health`, and
`graph_branches` (only failed / approval_required / stop_uncertain / blocked
branches). Attention items are raised for:

* a failed graph pipeline (join blocked);
* a branch that is failed / approval_required / stop_uncertain / blocked.

Cross-owner graph data is never shown; only owner-safe summaries (ids, states,
failure categories) — never raw commands, artifacts, or approval detail.

## Common operations

### Diagnose a stuck / failed graph
1. `pipeline-graph-health` — is anything failed / approval_required?
2. `pipeline-graph <id>` — read the branch states and the run failure code.
3. `pipeline-branches <id>` — find which branch failed and why (category only).

### Resume a failed graph
* Ensure the graph originated from a mission template with `build_graph`.
* `SAATHI_HARNESS_ADMIN=1 ... pipeline-graph-resume <id>` — reuses the dependency-
  closed set of valid verified checkpoints and reruns only invalidated branches and
  their descendants. Concurrent resume requests deduplicate to one via the recovery
  claim.

### Reconcile after a crash
* `pipeline-graph-reconcile` releases expired per-step claims so a fresh worker may
  reclaim them. Verified checkpoints are never re-executed; the join never runs
  twice without idempotency proof; uncertain execution fails closed.

## Safety invariants (do not weaken)

* Every executable step goes through `run_harness_action` and is independently
  verified.
* The join runs only after all required branches succeed and verify.
* A branch failure prevents the join; no partial success is ever reported.
* Approval and risk stay per-step; one branch cannot approve another.
* Ownership is end-to-end; cross-owner dependency / checkpoint / artifact / branch
  access is rejected.
* Trading Guardian remains unengaged; the graph layer opens no trading, broker,
  order, withdrawal, leverage, or transfer surface.
