# SaathiOS Retro-CRT UI — Work Loop

Self-paced loop. Each iteration: pick the highest-value **TODO**, then
**design → verify → build (rebuild+restart+visual check) → commit → mark DONE**.
Constraints: feature branch only (no push/merge); never modify frozen finance contracts
(64fb2b2b/a1136aa3/b771d761/4d685383/97fce540/b82233a0/e3e4e0b7/121f3f54/e9af80cd/8b9bbf57);
keep readability + green-up/red-down data semantics; reduced-motion aware.

Foundation shipped: global token retheme + CRT scanlines (`81d3a36a`); standalone demo
artifact `F1TpBqdoTwCdjgytQGcrc2`.

## Backlog (value-ordered)

1. **[DONE] Reusable retro utilities** — `.retro-panel` (corner brackets + red glow),
   `.retro-live[.ok]` (pulsing status dot), `.retro-glow` in `globals.css`.
2. **[DONE] Global shared-panel elevation** — red-tinted border + subtle red glow on all
   `.glass`/`.surface`/`.surface-raised`/`.surface-overlay` (border/shadow only, no layout
   change). Covers every page built on the shared Panel/Card primitives.
2b. **[DONE] Command Center showcase** — remapped the bespoke `command-hybrid.css`
   `.dl-*` palette (was blue-navy) to the retro CRT palette + mono font; ok/warn/crit
   kept functional green/amber/red.
3. **[DONE] Global status bar live pulse** — pulsing dot on "Local platform online"
   (every page). (Top-bar pulse optional, folded into showcases.)
4. **[DONE] Financial Browser live tape** — `MarketTape.jsx`: retro corner-bracket panel,
   real NEPSE index marquee + auto-scrolling per-symbol tape from NEPSE live + Financial
   Memory MARKET_OBSERVATION rows; honest `○ NO FEED / MARKET CLOSED` state (no fabricated
   trades); observation-only, no trading controls. On /finance/browser above Providers.
5. **[DONE] Accent cleanup** — NEPSE page had its own green-forest/cream palette
   (`nepse.css`): retinted neutrals to retro black/red, green tab underline → red, serif
   headings → mono; kept `--accent` green (up) + `--down` red for data. (design-lab.css
   blue local palette is a dev surface — minor, deferred.)
6. **[DONE] Home dashboard motion** — metric tiles count-up on real values (reuse
   `Counter`, no fabricated series/sparkline), red top-accent hairline + hover glow/lift +
   value glow; reduced-motion aware.
7. **[TODO] Font pass** — selective mono for headings/labels that still fall back to serif/
   sans; verify dense-table density before any global body flip.

## Log
- (foundation) 81d3a36a — global retro theme + CRT motion.
