# M58 — Visual QA

Screenshot-based review is mandatory; the redesign was not declared complete on colour
and blur alone. Screenshots in `docs/platform/m58_evidence/screenshots/`:
`platform_spatial_desktop`, `ops_constellation_desktop`, `ops_selected_drawer`,
`platform_mobile`, `platform_reduced_motion`.

## Reviewed dimensions
Hierarchy, spacing, clipping, readability, glow intensity, animation behaviour,
responsive layout, real API binding, safety-badge visibility, empty/loading/error
states.

## Defects caught BY visual/console review (and fixed)
1. **Core false-BLOCKED.** First desktop screenshot showed a red "SAATHI BLOCKED" core
   despite a healthy runtime. Root cause: `coreSignal` treated any gateway value other
   than ACTIVE/READY as down — but `TOOL_GATEWAY_ENFORCED` is the *healthy enforced*
   state. Fix: danger keys only off explicit failure words
   (down/degraded/fail/disabled/offline/error/unavailable). Re-verified: `SAATHI READY`
   cyan. Unit test added.
2. **SSR hydration mismatch.** Console review found 3 hydration warnings on the spatial
   pages (control page clean). Root cause: raw trig produced inline coordinates like
   `left:28.499999999999982%`; the browser reserialises SSR inline styles to `28.5%`
   before hydration, so React saw an attribute mismatch (cascading to zIndex/
   animationDelay). Fix: `round2`/`pct`/`pathD` emit 2-decimal, browser-stable values.
   Re-verified: 0 hydration warnings. Unit tests added.
3. **Cold-start empty cards.** The heavier spatial routes widened the first-hit cold
   window, occasionally leaving one ops card empty and collapsing the authenticated
   home. Fix: single sequential warm-up fetch + patient retry + always-mounted testid
   fallbacks. Re-verified across M54/M57/M58 certs.

## Result
All five screenshots reviewed and accepted: correct hierarchy, legible text on glass,
tuned glow, real data (api 127.0.0.1:8820 seeded BFF), safety badges present, no
clipping, mobile reflow correct, reduced-motion static render correct.
