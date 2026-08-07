# ACCESSIBILITY_REPORT — UI-NEXT-3

## Results (production `/command`)

| Scope | critical | serious |
| --- | --- | --- |
| Desktop hybrid root | 0 | 0 |
| Mobile hybrid root | 0 | 0 |

Tooling: axe-core via Playwright (`npm run cert:ui-next-3`).

## Fixes applied
- Mobile bottom nav: `role="tablist"` / `role="tab"` + `aria-selected`
- Causal chain: `role="group"` + `aria-label`
- Contrast tokens: `--dl-muted` / `--dl-sec` raised for graphite AA
- Production shell remains visible (not hidden as design-lab)

## Other
- Keyboard Tab exercise recorded in browser cert
- Reduced-motion class `dl-reduced` / `prefers-reduced-motion`
- Touch targets ≥44px on mobile nav
