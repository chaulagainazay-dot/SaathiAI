# M59 — Accessibility Automation (Workstream 9)

Verdict: **ACCESSIBILITY_AUTOMATION_PASSED_WITH_LIMITATIONS**

Tool: **axe-core** (`node_modules/axe-core`) injected into headless Chromium by
`scripts/m59_browser_cert.mjs`, run on: `/platform`, `/platform/ops`,
`/platform/missions`, mission detail, `/platform/agents`, agent detail,
`/platform/approvals`, approval detail, `/platform/attention`, command palette open.

## Result

- **Critical violations: 0** (hard gate `accessibility_no_critical` PASS).
- **Serious violations: 10**, all pre-existing app-shell/M58 chrome (see below),
  none introduced by M59 surfaces.

### Critical fixed during M59

The spatial command palette originally failed `aria-required-parent` (options not
direct children of a `listbox`). Fixed by flattening to a `role="listbox"` with
`role="option"` direct children and presentational group headers. Additionally, the
pre-existing **global** app-shell palette was opening on workspace routes and
contributing its own `aria-required-parent`; the spatial shell now wins ⌘K via a
capture-phase handler so only the axe-clean spatial palette opens.

### Serious remaining (documented, accepted)

| Rule | Source | M59? |
|---|---|---|
| color-contrast | global TopBar chrome ("Local", "Alerts" status glyph text) | No — pre-existing |
| list | M58 `/platform` module panels (`#mod-missions`, `#mod-attention` `<ul>` with non-`<li>` children) | No — M58 |

M59 also **remediated** the global sidebar `shell-nav-group-label` contrast
(raised from `--text-faint` ≈2.5:1 to `--text-secondary`) and raised the spatial
`--text-muted` token to ≥4.5:1, clearing those serious violations app-wide.

## Manual keyboard / structure checks (in-harness)

- Command palette + context drawer are keyboard operable and Escape-closable.
- Visible focus rings on dock items, chips, cards, palette input, drawer close.
- Landmarks: `nav[aria-label="Workspace navigation"]`, breadcrumb `nav`, dialog
  roles with modal semantics and labels. Status not by colour alone (StatusPulse +
  text labels). Reduced motion respected.

## Limitation

Automated axe checks are **not** a complete WCAG certification. A broader manual
audit (screen-reader walkthroughs, cognitive/AT testing) is not claimed.
