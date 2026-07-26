# M59 — Residual Limitations

Honest scope boundaries of the M59 delivery.

## API-shaped limitations (read-only where no safe API exists)

- **No per-mission API.** Mission detail composes the mission list record with
  related runtime records by `mission_id`; last-operator-action and final-result
  fields are not exposed by any endpoint and render as sentinels.
- **No approve/acknowledge/resolve for attention.** Attention items are executions;
  the only governed mutation offered is `cancel` (when eligible). Resume/reconcile
  remain on the Operations workspace.
- **Mission actions.** No mission lifecycle-transition API exists beyond create, so
  Mission Control is inspect + navigate; no frontend-only transitions were invented.
- **Approvals single-GET.** No `GET /approvals/{id}`; detail selects the record from
  the authorized all-status list and refetches after decisions.

## Certification limitations

- **Accessibility:** axe-core automation only — `ACCESSIBILITY_AUTOMATION_PASSED_WITH_LIMITATIONS`.
  0 critical; 10 serious remain, all pre-existing global TopBar chrome + M58
  `/platform` list semantics (none on M59 surfaces). Not a full WCAG audit.
- **Performance:** local lab budgets only — `LOCAL_PERFORMANCE_BUDGETS_PASSED`.
  Real-user Core Web Vitals not yet available.
- **Responsive:** automated at 390px for three list workspaces + CSS review of four
  breakpoints; not an exhaustive per-route device-matrix capture.
- **Fixtures:** certification uses deterministic, isolated, test-only fixtures in a
  throwaway DB.

## Platform posture (unchanged, enforced)

Production unauthorized · multi-host disabled · connectors dry-run · financial and
trading execution disabled · trading guardian advisory-only · localhost-only · no
push / merge / deploy performed.

## Pre-existing debt surfaced (not fixed by M59, out of scope)

- Global app-shell TopBar status glyphs ("Local"/"Alerts") have low contrast.
- M58 `/platform` module-panel `<ul>`s contain non-`<li>` children (axe `list`).

These affect the shared chrome / M58 page, not the M59 workspaces, and are left for
a dedicated chrome-a11y pass.
