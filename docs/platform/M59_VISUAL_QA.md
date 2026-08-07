# M59 — Visual QA (Workstream 12 evidence)

15 screenshots captured by the production cert into
`docs/platform/m59_evidence/screenshots/`:

`platform`, `ops`, `missions`, `mission_detail`, `agents`, `agent_detail`,
`approvals`, `approval_detail`, `attention`, `command_palette`, `context_drawer`,
`reduced_motion`, `mobile_missions`, `mobile_approvals`, `mobile_attention`.

## Review criteria + findings

| Criterion | Finding |
|---|---|
| Hierarchy | Clear — status strip → title/breadcrumb → content; section panels with signal edges |
| Contrast | Essential text ≥4.5:1 after M59 token/label remediation (see accessibility doc) |
| Clipping / overflow | None at desktop or 390px mobile (no horizontal scroll) |
| Glow intensity | Restrained — signal edge only on relevant frames, not every element |
| Focus visibility | Visible rings on dock, chips, cards, palette, drawer |
| Connection accuracy | Mission lineage + agent legend show real governed relationships, not decorative paths |
| Authority clarity | Advisory vs execution-capable labelled; approval scope/expiry explicit |
| Severity clarity | Attention lanes Critical/High/Medium/Informational with pulses, never hover-only |
| State truthfulness | Missing data → Unavailable/Unknown/—; no fabricated values |

## Defects found and fixed during M59

1. **Critical axe `aria-required-parent`** in command palette → flattened listbox;
   suppressed conflicting global palette on workspace routes.
2. **Color-contrast serious** on spatial muted text + global sidebar labels →
   raised `--text-muted` and `.shell-nav-group-label` to legible tokens.
3. **Dev-mode route flake** (on-demand compile timing) → production build is the
   authoritative precompiled gate; both dev and build reach PASS.

## Consistency

Glass Frame design system applied uniformly across all eight routes: semantic
tokens, cyan operational / amber authority / red blocked / muted inactive /
verified-only green, deep navy canvas, readable glass surfaces.
