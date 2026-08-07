# M58 — Residual Limitations

Honest scope boundaries. M58 delivered the Glass Frame system and transformed the two
certified surfaces (`/platform`, `/platform/ops`) end-to-end. The following are
represented on the home as live glass panels/nodes but NOT yet built as separate,
full spatial screens:

- **Mission Control (Screen 3)** — execution lifecycle, attention reasons, and
  timelines are shown as glass panels + the Missions node; a dedicated standalone
  spatial execution-graph screen is deferred to M59. `/missions` remains the list view.
- **Agents constellation (Screen 6)** — agent bindings render as a glass panel with
  full lifecycle controls + the Agents node; a standalone agents constellation is
  deferred. No autonomous capability is claimed (advisory/limited authority shown).
- **Approval Center (Screen 4)** — pending approvals surface as an amber panel + link;
  a dedicated full approval-center screen with per-request risk/evidence/expiry
  hierarchy is deferred. Controls remain server-authorized.
- **Runtime Attention field (Screen 5)** — attention items render in an amber panel
  grouped by runtime state/reason; a standalone "signals entering a field" screen with
  Critical/High/Medium/Informational grouping is deferred.

Other limitations:
- The command palette remains the existing shell ⌘K; no spatial-specific palette added.
- The spatial scope is applied to `/platform` and `/platform/ops` only; the shared app
  shell (left rail, top clock) is unchanged and out of M58 scope.
- Certification ran in Next.js dev mode (as M54–M57). `cert:m58:build` exists for a
  prod-build run but was not executed this session.
- Accessibility: no automated axe-core pass; mono micro-label contrast sweep and an
  AT-facing text "system map" summary are recommended for M59.
- Performance was reasoned + measured by route weight and cert responsiveness, not by a
  formal Lighthouse/CWV budget assertion in the cert (recommended for M59).

None of these limitations weaken any safety boundary; all safety labels remain visible
and truthful.
