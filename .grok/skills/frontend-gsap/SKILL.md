---
name: frontend-gsap
description: >
  SaathiOS-adapted GSAP guidance for HyperFrames HTML→video, Mr. Yeti motion,
  and frontend animation. Use when writing GSAP tweens/timelines, HyperFrames
  compositions, kinetic typography, scroll/UI animation, or reviewing animation
  performance on low-RAM targets. Adapted from greensock/gsap-skills (MIT);
  does not vendor the upstream repo.
license: MIT (adapted patterns; upstream greensock/gsap-skills is MIT)
---

# Frontend GSAP (SaathiOS)

## Source and boundary

- **Upstream:** [greensock/gsap-skills](https://github.com/greensock/gsap-skills) (Skill type; MIT).
- **SaathiOS status:** `REGISTERED` / skill foundation only — **not** a runtime service.
- **Does not replace:** HyperFrames CLI, render adapters, ExecutionGateway, or video directors.
- **License note:** GSAP library licensing is separate from this skill. Prefer the officially free GSAP surface documented at gsap.com; do not assume Club plugins unless licensed. CDN usage in `saathi/tools/hyperframes.py` must stay within allowed terms.

## When to use

- HyperFrames / HTML compositions for Mr. Yeti or social clips.
- Timeline-driven motion (intro → beat → CTA).
- Preferring transform/opacity animation for 8 GB Mac + Chrome render path.

## Core patterns (adapted)

```javascript
// Prefer transforms + autoAlpha (compositor-friendly)
gsap.to(".card", { x: 40, y: -8, autoAlpha: 1, duration: 0.6, ease: "power2.out" });

// Timeline with labels for deterministic HyperFrames scenes
const tl = gsap.timeline({ defaults: { duration: 0.45, ease: "power2.out" } });
tl.addLabel("intro", 0)
  .from(".title", { y: 24, autoAlpha: 0 }, "intro")
  .from(".sub", { y: 16, autoAlpha: 0 }, "intro+=0.15")
  .to(".cta", { scale: 1.04, yoyo: true, repeat: 1 }, "intro+=0.5");
```

### Rules for SaathiOS renders

1. **Determinism:** Prefer fixed durations and labels over random staggers when output must be reproducible.
2. **Transforms only:** Prefer `x`, `y`, `scale`, `rotation`, `autoAlpha` over `top`/`left`/`width`/`height`.
3. **Cleanup:** Use `clearProps` or leave final state intentional for freeze-frame end cards.
4. **Reduced motion:** If designing interactive web UI (not pure render), respect `prefers-reduced-motion` via `gsap.matchMedia` when applicable.
5. **No secrets in animation payloads:** Never embed tokens, emails, or private paths in HTML templates.

## HyperFrames integration

- Entry: `saathi/tools/hyperframes.py` (HTML + GSAP → `npx hyperframes render`).
- Keep scenes short; long timelines increase Chrome+FFmpeg memory on 8 GB machines.
- Resource class for heavy multi-scene work: `ON_DEMAND_LOCAL` only.

## Pitfalls

- Multiple `from()` on the same property without `immediateRender: false` can hide later tweens.
- Infinite `repeat: -1` is fine for preview loops; for final MP4, prefer finite timelines that end on a hold frame.
- Do not introduce a second animation stack (Framer Motion + GSAP) for the same HyperFrames scene without reason.

## Disable / rollback

- Skill-only: remove or disable via Grok `[skills] disabled = ["frontend-gsap"]`.
- Runtime GSAP CDN line is independent; changing it is a separate code change.
