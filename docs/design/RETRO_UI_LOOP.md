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
2. **[TODO] Command Center showcase** — framed retro panels + live pulse on `/command`
   (primary surface; the reel's signature framed look).
3. **[DONE] Global status bar live pulse** — pulsing dot on "Local platform online"
   (every page). (Top-bar pulse optional, folded into showcases.)
4. **[TODO] Financial Browser showcase** — retro-panel framing + the live auto-scrolling
   tape component fed by read-only market/memory data (observation-only, no trading).
5. **[TODO] Accent cleanup** — retint stray green/blue (tab underlines, links) to the red
   family where not carrying semantic meaning; keep green-up/red-down data.
6. **[TODO] Home dashboard motion** — animated metric tiles + sparklines on `/`.
7. **[TODO] Font pass** — selective mono for headings/labels that still fall back to serif/
   sans; verify dense-table density before any global body flip.

## Log
- (foundation) 81d3a36a — global retro theme + CRT motion.
