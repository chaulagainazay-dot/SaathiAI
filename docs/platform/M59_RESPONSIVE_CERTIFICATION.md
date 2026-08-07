# M59 — Responsive Certification (Workstream 11)

Verdict: **RESPONSIVE_SPATIAL_WORKSPACE_CERTIFIED**

## Automated (cert harness, 390×844)

`responsive_mobile` hard gate PASS across `/platform/missions`,
`/platform/approvals`, `/platform/attention`:

- **No horizontal overflow** (`document.scrollWidth ≤ innerWidth`).
- **Navigation present** (`nav[aria-label="Workspace navigation"]`) — the dock
  becomes a bottom bar, not a shrunken desktop rail.
- ⌘K FAB appears; `workspace-main` gains bottom padding to clear the dock.
- Context drawer becomes a full-screen bottom sheet.

Screenshots: `mobile_missions.png`, `mobile_approvals.png`, `mobile_attention.png`.

## Breakpoint behaviour (CSS)

| Width | Behaviour |
|---|---|
| 390×844 (phone) | bottom dock, FAB, full-screen drawer sheet, stacked cards (grid `minmax(280px,1fr)` collapses to 1 col) |
| 768×1024 (tablet) | single-column grid → multi as width allows; dock still bottom bar ≤820px |
| 1280×800 (laptop) | left rail dock, right-side drawer, multi-column card grids |
| 1440×900 (desktop) | same as laptop with wider `max-width: 1160` content column |

Spatial lists degrade to grouped/stacked cards and accessible lists rather than a
forced constellation. Safety status (the persistent SafetyBoundaryBadges) remains
visible at every width. Touch targets use ≥40px chips/buttons.

## Limitation

Automated checks covered the three list workspaces at 390px plus CSS review of the
four breakpoints; exhaustive per-route device-matrix screenshots were not captured
for every breakpoint.
