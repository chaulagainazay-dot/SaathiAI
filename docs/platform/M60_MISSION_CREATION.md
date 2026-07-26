# M60 — Guided Mission Creation

Route: `/platform/missions/new`. Behavior: **LIVE** — mission creation is the real
`POST /missions`.

Guided stepper: Intent → Scope → Objective & risk → Review. Local draft autosave
(`saathi_m60_mission_draft`) with a draft-recovery banner (resume/discard).

- **Scope**: shows org/workspace/owner/role; requires a project. Projects are
  fetched from `/projects`; a new project can be created inline via `POST /projects`.
- **Risk** is operator-selected and explicitly labelled "not an authoritative policy
  result".
- **Submit**: `missionCreateBody()` derives a deterministic `{project_id, key, name}`
  (slug key, no Date/random). After `POST /missions` the flow refetches `/missions`
  and confirms the record exists server-side before showing "Mission created"
  (`ServerReconciliationState`: submitting → server_accepted → reconciled). Never an
  optimistic created state.
- Role-gated: `create_mission` permission via `actionPermission(role)`;
  `RoleBoundaryNotice` explains insufficient permission. Server still enforces auth.
