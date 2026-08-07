# M60 — Role-Aware Actions

`ROLE_ACTION_MATRIX` + `actionPermission(role, action)` map real platform roles
(viewer/operator/owner/admin/system) to permission states: permitted /
requires_approval / insufficient / unavailable / read-only / unknown. A viewer sees
no active decision/create controls; an operator sees permitted operational actions.
`RoleBoundaryNotice` explains the boundary in-UI, and every server action still
enforces authorization independently — the UI is not the security boundary.
