# M59 — Mission Control (Workstream 1)

Routes: `/platform/missions` (list) · `/platform/missions/[missionId]` (detail).

## Data binding (real APIs only)

- List: `GET /api/v1/platform/missions` → `MissionLinkRecord.to_public()`
  (`mission_id, project_id, org_id, workspace_id, key, name, owner_id, status, created_at`).
- There is **no per-mission API**. Detail composes the mission record (located in
  the authorized list) with related runtime records that carry its `mission_id`:
  executions (`/runtime/executions`), approvals (`/approvals`), attention
  (`/runtime/attention`), and agent bindings (`/agent-bindings`).

`normalizeMission()` derives active-execution / pending-approval / attention
counts by matching `mission_id`. Missing fields render as `Unavailable` / `Unknown`
— never fabricated.

## List

Spatial mission cards (glass nodes with a signal edge) in a responsive grid that
degrades to a stacked list; not forced into a graph when large. Filter by status,
search by name/key/id, sort by activity/risk/status. Each card → detail; an
Inspect button opens the context drawer for quick inspection.

## Detail — execution lineage

Renders the canonical governed chain as a real dependency path:

```
Objective → Stages → Agents → Approvals → PlatformAgentRuntime
          → ExecutionGateway → Registered Tools → Evidence
```

Sections: mission identity, runtime state (active/total/approvals/attention),
assigned agents (→ agent detail), approval junctions (→ approval detail), related
attention (→ attention detail), executions & evidence. Copy is explicit that the
browser holds no execution authority and that evidence export is governed on the
Operations workspace.

## Actions

Read + navigate only. No mission action API exists beyond create (owned by the
existing form flow), so no frontend-only state transition is offered. Empty/error
states: no missions, mission unavailable/deleted (Object not found), partial data,
server unavailable — all fail safely.
