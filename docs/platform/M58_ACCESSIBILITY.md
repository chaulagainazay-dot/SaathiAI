# M58 — Accessibility

## Implemented
- **Semantic controls** — module nodes and ops node headers are real `<button>`s;
  no nested interactive elements (ops node header separated from run buttons).
- **Non-colour status** — every signal pairs colour with text/glyph: `StatusPulse` has
  `role="img"` + `aria-label` (e.g. "Approvals Attention"); core has an aria-label
  describing state; badges carry text.
- **Labels** — nodes: `aria-label="<Module>. <detail>. Open <Module>."`; core:
  `"Saathi core — <STATE>. <sentence>."`; drawer: `aria-label` + labelled close button.
- **Current state** — selected node exposes `aria-current="true"`.
- **Focus** — `:focus-visible` ring on nodes (`--focus-ring`), keyboard-operable.
- **Live regions** — `SystemStatusStrip` uses `role="status" aria-live="polite"`;
  loading uses `role="status"`, errors `role="alert"`.
- **Reduced motion** — full support (see M58_MOTION_SYSTEM).
- **Scalable text** — token-based `--fs-*`; no fixed tiny text on essential info.
- **Touch** — compact grid nodes are full-width, ≥44px targets.
- **Contrast** — glass surfaces darkened + text tokens (`--text-primary/secondary/
  muted`) chosen so essential text meets AA on the dark canvas.

## Verified
M58 cert: `no_page_errors`, keyboard-driven `module_navigation` (click→aria-current),
`reduced_motion`, `responsive_mobile`. Screen-reader labels present in DOM.

## Known limitations (WITH_LIMITATIONS)
- Decorative mono micro-labels (10–11px) exist for eyebrows/counts; essential values
  are larger. A full AA sweep of every mono micro-label contrast ratio is recommended
  in M59.
- Connection SVG is `aria-hidden` (decorative); the same relationships are conveyed by
  node labels and in-page panels, but a text "system map" summary for AT is a future add.
- No automated axe-core run in this cert; manual/label-based verification only.
