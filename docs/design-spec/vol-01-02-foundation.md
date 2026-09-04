# THE DHAAGO SPECIFICATION
## SaathiOS Master Product Design Bible · v1.0 · July 2026

**Dhaago** (धागो, "thread") — the single thread that ties every SaathiOS application into one family. This document is the permanent source of truth for every designer, developer, AI agent, and future contributor. Nothing ships that contradicts it; anything it doesn't cover gets added to it through Governance (Volume 18), never invented ad-hoc.

**Applications governed:** HCG OS (hospital cafeteria) · IELTSAlert · SaathiOS Console · future Travel, Trading, CRM, ERP, AI Business apps.

**Reconciliation note (binding):** two design languages predate this bible — SOVEREIGN_ORBIT (SaathiOS Console: navy, dark-first, saathi-blue) and Chulo (HCG OS 2.0: emerald, light-first). Dhaago does not replace them; it **promotes their shared DNA to the platform layer** and demotes their differences to the App Accent Layer (Vol 7). Both remain valid expressions of one system.

---

# VOLUME 1 — PLATFORM VISION

## 1.1 Purpose
Define why SaathiOS exists and the non-negotiable philosophy every product decision inherits.

## 1.2 Mission
> **Give one person the operating leverage of an organization.**
Every SaathiOS app turns a messy real-world operation — a canteen, an exam prep journey, a trading book, a travel business — into something one owner can see, decide, and act on in minutes a day, with AI carrying the routine.

## 1.3 Product philosophy
1. **Operator software, not office software.** Users are standing, rushing, mid-task. Software must respect the posture of work (Vol 2). Benchmark: Square in a restaurant, not Excel in a cubicle.
2. **Attention is the spine.** The system's first job is triage: *what needs me now?* Every app's home answers this before showing anything else. (Inherited from SaathiOS IA principle #1; generalized platform-wide.)
3. **Trust through evidence.** Numbers link to their sources. AI answers cite tables. Money movements leave audit trails. Never fabricate; render "not measured" honestly.
4. **One door per job.** Every capability has exactly one canonical place. Duplicated entry points are IA bugs.
5. **The domain is the moat.** Nepali payroll advances, ward-level credit, ZKTeco punches, IELTS band math — deep domain fit beats generic polish. Design amplifies domain features; never sands them off to look like a template.

## 1.4 Design philosophy
- **Calm, premium, legible.** Not neon, not casino, not glass-everywhere (SOVEREIGN_ORBIT brief, now platform law). Excitement comes from *speed and correctness*, not decoration.
- **Form encodes state.** Status is shape + label + color, never color alone. A screen's visual weight maps to operational urgency.
- **Density is a dial, not a fork.** Beginner and Expert see the same structure at different densities (progressive disclosure), never different apps.
- **Delight budget: three moments per app.** Signature micro-interactions are chosen deliberately (e.g., HCG's flying cart dot, payment check-draw, inbox all-clear). Everything else is utility motion.

## 1.5 Core principles (the Ten Threads)
Every screen review (Vol 18) scores against these:
1. One primary action per screen.
2. Everything important within one tap/keystroke of the surface home.
3. Exception-based UI — quiet when nothing needs you; "All clear" is a valid, designed state.
4. Readable at the working distance of its surface (30cm phone / 40cm till / 2m kitchen).
5. Zero training required for staff roles; power depth for operators (palette, shortcuts, bulk).
6. Undo over confirm; preview over apology.
7. Offline-tolerant where money or food moves.
8. Every number traceable to source.
9. Authority visible, never bypassable (approvals, risk, simulated-vs-live).
10. Same gesture means the same thing everywhere (Vol 9 grammar).

## 1.6 Brand identity
- **Platform mark:** "Saathi" wordmark, saathi-blue `--saathi-500 #5f8fff` on navy or white. Apps carry their own accent (Vol 7 App Accent Layer) plus the platform badge in About/Settings — "A SaathiOS product."
- **Voice:** a competent friend (साथी). Plain sentences, active verbs, no exclamation inflation, bilingual-ready. Says "Rs 4,500 overdue from Ward B" not "Uh oh! Some payments look late!"
- **Naming rule:** features get human job names (Inbox, Cash Book, Count Mode), never system names (NotificationCenterV2, LedgerModule).

## 1.7 Product values → design consequences
| Value | Consequence |
|---|---|
| Speed | Interaction→paint <100ms on operator surfaces; optimistic UI default (Vol 15) |
| Clarity | 12px text floor; one primary per screen; labels on all icons |
| Scalability | 3-layer tokens; capability-based nav config; app = accent + IA instance |
| Accessibility | WCAG 2.2 AA is a release gate, not a backlog item (Vol 14) |
| Consistency | 16-component library is the only UI vocabulary (Vol 8) |
| Maintainability | Lint-enforced: no hex in components, no inline styles, no native dialogs (Vol 16) |
| AI integration | AI is ambient presence with three modes (Vol 13), never a page |

## 1.8 Anti-patterns (Volume 1)
- ✗ "Dashboard as brochure" — stacking every widget at equal weight.
- ✗ Aesthetic dark mode that inverts colors without redesigning contrast.
- ✗ Feature pages named after backend modules.
- ✗ Per-app reinvention of buttons, dialogs, toasts "because our app is different." Your app is an accent, an IA, and workflows — never new primitives.

## 1.9 Developer notes
- This bible lives at `docs/design-spec/` in the SaathiAI repo; apps vendor a copy or link it in their CLAUDE.md. AI coding agents: load Volumes 5–10 before generating any UI; load Volume 16 before generating any component file.
- Precedence: user's explicit instruction > this bible > app-local docs > model defaults.

---

# VOLUME 2 — USER RESEARCH & CONTEXTS

## 2.1 Purpose
Ground every rule in real humans and real rooms. Personas here are drawn from live operations (HCG staff roster, SaathiOS operator, IELTS learner) — not invented archetypes.

## 2.2 The five platform personas
**P1 — The Operator (Ajay).** Owner of everything. Phone in pocket 14h/day, desktop at night. Checks in 5-minute bursts. Wants: is today okay, what needs me, one-tap approve. Fears: silent failures, money leaks. Expert-mode user; lives in ⌘K and Inbox.

**P2 — The Counter (Sajana).** Standing at till 8h/day. Two-finger typist. Speed is identity — a slow POS embarrasses her in front of a queue. Wants: 4-touch sale, instant credit lookup. Never opens settings.

**P3 — The Maker (Yabesh, kitchen).** Wet/greasy hands, 2m from screen, ambient noise, heat. Reads glances, not paragraphs. Wants: what to cook next, batch quantities, one-motion bump. Any typing is design failure.

**P4 — The Crew (Aryan, helper).** Minimal smartphone literacy, budget Android, 2 minutes/day of app use. Wants: am I clocked in, what are my duties, submit report, see salary. Trust matters: attendance and pay must be visible and fair.

**P5 — The Learner/Client (IELTS student; future travel customer).** Consumer expectations (Instagram-grade polish), self-serve, mobile-only, notification-driven. Wants progress made visible and next action obvious.

## 2.3 Journey maps (canonical three)
**Operator's day:** 07:00 phone glance (Home pulse + overnight Whispers) → 10:00 Inbox sweep (approve 3, reject 1) → lunchtime watch live orders → 20:00 close-day ritual (wizard) → 21:00 digest arrives in Telegram. *Design target: total screen time <20 min.*
**Counter's rush:** queue of 8 → repeat-customer chip → charge → drawer → next. *Target: <15s/sale, zero navigation events during rush.*
**Crew's day:** punch machine → phone shows "In ✓ 9:02" → duty list ticks → 15:00 break timer → 20:00 report nag → submit → done. *Target: <3 min total.*

## 2.4 Pain points (from audit evidence, permanent regression list)
Illegible 10px text · native browser prompts mid-workflow · nav duplication · spinner-only loading · raw server errors shown to staff · hover-only affordances on touch devices · UTC dates in a UTC+5:45 country. These seven are **banned regressions** — any reappearance fails design review (Vol 18).

## 2.5 Environment standards
| Environment | Facts | Binding rules |
|---|---|---|
| **Hospital canteen** | Glare, steam, noise, gloves, power cuts, flaky wifi, Moto-G-class devices | KDS dark-first ×1.6 type scale; 72px bump targets; offline queues; one chime max; battery-frugal polling |
| **Counter/till** | Standing, queue pressure, cash drawer | Fullscreen surface, no chrome; 56px primaries; keyboard path complete; offline sale queue |
| **Office/desk** | Desktop or phone, quiet, analytical | Density toggle; tables with keyboard nav; export everywhere; multi-column ≥1280px |
| **On-the-move** | Phone, one thumb, sunlight | Bottom-reachable primaries; pull-refresh; system font scale respected |
| **Consumer (IELTS/Travel)** | Personal phone, evening use | Larger type default, softer density, notification etiquette (Vol 13 caps) |

## 2.6 Device matrix (test floor)
Budget Android (Moto G / Redmi, 360×800, 4G) = the floor; iPhone SE→Pro; 10" Android tablet (KDS/till); 1366×768 laptop; 1440p desktop. Every release certifies on the floor device first (Vol 18 checklist).

## 2.7 Anti-patterns (Volume 2)
- ✗ Designing on a 27" monitor and "checking" mobile.
- ✗ Personas as posters — if a rule can't cite a persona+environment, it's taste, not design.
- ✗ Treating the Crew as "basic users" — they are expert *at their job*; the UI must be expert at fitting it.

## 2.8 Developer notes
Playwright viewport suite must include 360×800 and 1024×768-landscape (tablet). Type-scale and contrast checks run against the environment table above, not generic breakpoints.
