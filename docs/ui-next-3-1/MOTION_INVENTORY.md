# UI-NEXT-3.1 — Production Command Motion Inventory

**Authority:** `docs/design/SAATHIOS_DESIGN_DNA.md` · `docs/design/SAATHIOS_MOTION_LANGUAGE.md`  
**Surface:** Production Hybrid Command `/command`  
**Audit base:** `60166002c1d16fbae09c23f3a9196da1762e0edb`

## Classification key

| Class | Meaning |
| --- | --- |
| `NO_MOTION` | State swap only; no transition |
| `CSS_SUFFICIENT` | Tokens + CSS transitions/keyframes |
| `WEB_ANIMATIONS_API` | Cancelable multi-step without GSAP |
| `GSAP_JUSTIFIED` | Coordinated multi-panel choreography only |
| `LOTTIE_JUSTIFIED` | Bounded high-quality vector state asset |

**Default:** `CSS_SUFFICIENT`

## Inventory

| Interaction | States / notes | Class | Rationale |
| --- | --- | --- | --- |
| Saathi Core orb | IDLE→CLOSED voice vocabulary | `CSS_SUFFICIENT` | Color + bounded loops per Motion Language |
| Voice state label | Same vocabulary | `NO_MOTION` / badge | Text truth; reduced-motion primary |
| Listen button → LISTENING | User intent | `CSS_SUFFICIENT` | Orb + pill only |
| Ask → THINKING→SPEAKING | Simulated consumer path | `CSS_SUFFICIENT` | Short hold; no fake % |
| Mode tabs COMMAND/AGENTS/INVESTMENTS/EVIDENCE | Context preserve | `CSS_SUFFICIENT` | 150–220ms panel emphasis; no full-page fade |
| Mobile bottom nav | Same modes | `CSS_SUFFICIENT` | Match desktop tokens |
| Attention item select | Rank colors | `CSS_SUFFICIENT` | Border/focus only |
| Risk status | HEALTHY/WARNING/BREACHED/DATA_INSUFFICIENT/RECONCILIATION_REQUIRED | `CSS_SUFFICIENT` | Transition flash on change only; no permanent pulse |
| Risk budget bars | fill width | `CSS_SUFFICIENT` | width transition; status color |
| Proposal lifecycle | DRAFT…STALE_PROPOSAL | `CSS_SUFFICIENT` | Border/tone; never green “executed” |
| Current → proposed compare | trade row select | `CSS_SUFFICIENT` | Synchronized emphasis class |
| Why? expand | reason codes | `CSS_SUFFICIENT` | Height/opacity enter |
| Performance panel | NAV/return/DD/PnL/contrib | `CSS_SUFFICIENT` | Metric enter; no chart fireworks |
| Agent nodes | ACTIVE/WAITING/… | `CSS_SUFFICIENT` | Status border; no continuous busy |
| Mission stages | stage label | `CSS_SUFFICIENT` | Badge tone |
| Evidence select / link highlight | real `related_ids` only | `CSS_SUFFICIENT` | Related ring |
| Loading / error / stale | banners | `NO_MOTION` or fade | Instant under reduced-motion |
| Focus rings | keyboard | `NO_MOTION` | Always instant |
| Multi-panel evidence/mission choreography | n/a at ship | `GSAP_JUSTIFIED` deferred | CSS covers single emphasis |
| Saathi/Yeti Lottie | no asset | `LOTTIE_JUSTIFIED` deferred | No local asset |
| 3D / WebGL | n/a | DEFER Three.js | Forbidden on Command |

## Technology decision

```text
CSS_SUFFICIENT (primary)
WEB_ANIMATIONS_API — not required
GSAP_RUNTIME_DEFERRED
LOTTIE_RUNTIME_DEFERRED
THREE_JS_DEFERRED
```

## Reduced motion

When `prefers-reduced-motion: reduce` (or `.dl-reduced` / `html.dl-reduced-root`):

- Kill loops (pulse, shimmer, speak glow animation)
- Kill mode enter choreography
- Preserve labels, icons, colors, focus, instant state swap
- Budget bars jump to width without animation

## Performance constraints (8 GB Apple Silicon)

- No continuous idle GPU/animation except optional LISTENING/SPEAKING loops while active
- Transform/opacity preferred; box-shadow pulses only on active voice states
- No permanent red risk pulse
- Bundle: CSS-only motion tokens; zero GSAP/Lottie/Three runtime delta
