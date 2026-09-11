# SaathiOS — Orbit design direction

**Date:** 2026-09-04
**Reference studied:** Reznikov Engineering / **Apex** ("autonomous AI chief of staff"), Facebook page, 19K followers.
**Status:** Milestone 1 shipped (`/orbit`). Milestones 2–4 specified below.

---

## 1. Why this reference matters

Apex is the closest public analogue to SaathiOS: a single operator running a business
through a fleet of specialist agents. Their most-viewed content (38K, 18K, 12K views)
is not a feature demo — it is **one screen**: a glowing core with named specialists in
orbit (Strategist, Researcher, Finance, Chief of Staff, Sales, Memory, Marketing,
Design, Ops, Social, Engineering, CRM) connected by luminous edges.

The lesson is not the glow. It is that **the system's shape is the product**. One
image answers "what do I actually own?" — something 135 table-based routes cannot do.

### What they do well
- **A single canonical view of the whole system.** Core + satellites, instantly legible.
- **Identity through structure**, not decoration — the constellation *is* the brand.
- **One warm focal point** on a cool field. The eye lands on the core every time.
- **Named roles, not service names.** "Chief of Staff", not `orchestrator-svc`.

### What we deliberately do NOT copy
Their register is high-glow, near-neon, cinematic. Our own design system already
forbids that: *"premium, calm, legible; **not** neon, not casino, not glass-everywhere."*
Copying the bloom would break our system and read as imitation. We take the
**structure**, render it in **SOVEREIGN_ORBIT**: deep navy ground, one amber core,
cool low-alpha edges, clinical mono labels, hairline glow.

---

## 2. Honest audit of where we started

| Metric | Audit (Jul 2026) | Measured 2026-09-04 |
|---|---|---|
| Inline `style={{…}}` sites | 1,595 | **2,682** (+68%) |
| Hardcoded hex colours | — | **766** |
| `var(--…)` usages | ~12 tokens existed | 1,305 |
| Route pages / components | — | 135 / 56 |

The token architecture (primitive → semantic → component, dual-theme) **landed**.
Adoption did not keep pace: hand-styling is outrunning the system. The consequence is
concrete — no central design change is currently possible.

**We had no view of the system as a whole.** Every surface is a table or a panel grid.
That is the actual missing part, and it is what Apex has and we did not.

---

## 3. Milestone 1 — Orbit (shipped)

Route `/orbit`. A core (SaathiOS) with 14 specialists in two tiers; colour is state,
ring distance is tier, edges are reporting lines.

**Built to be the reference implementation for the token migration:**
- **Zero hardcoded hex** across all four files — enforced by a test that fails the
  build if a hex literal appears.
- Adds exactly **two** component tokens (`--orbit-core`, `--orbit-edge`), both mapped
  from existing primitives (`--color-amber-500`, `--color-cyan-500`). The palette stays
  under the design system's control.
- All status colour resolves through `var(--status-*)` — the same 8 semantic states the
  existing `StatusBadge` uses, so orbit and badges can never disagree.

**Geometry is pure and deterministic** (`lib/orbit.js`): same roster → same coordinates,
every render. No randomness, no time dependence — the constellation never reshuffles
under the operator's cursor, and layout is unit-testable without a DOM.

**Read-only by construction.** Selecting a node reveals detail; the surface exposes no
command, and a test asserts it. Consistent with the trading program's authority model.

**Accessible, not image-only.** `role="img"` with a live text equivalent
("14 agents in orbit; 9 healthy, 1 needing attention. Worst state: warning."), a visible
legend, keyboard-selectable nodes (Enter/Space), visible focus, and
`prefers-reduced-motion` honoured.

**Worst-first summary.** One `danger` agent outranks fifty healthy ones. An operator
must never see an average that hides a failure.

---

## 4. Milestones 2–4 (specified, not yet built)

### M2 — Live data binding
Replace the static roster with the fleet/orchestration BFF and the read-only
`command_surface` aggregator built for the trading program (MARKETS / RESEARCH /
PORTFOLIO / TRADING / SAFETY). Unknown state must render as `UNKNOWN`, never as healthy —
the aggregator already guarantees this.

### M3 — Token enforcement pass
The real prize. Convert the 766 hardcoded hex values and the worst inline-style
offenders to semantic tokens, then add the orbit test's hex assertion as a **repo-wide
lint gate** so the count can only go down. Target: hex literals → 0 in `app/` and
`components/`; inline styles below the original 1,595 audit baseline.

### M4 — Orbit as the shell
Promote orbit from a route to the **entry surface**: land on the constellation, click
through to the detail route. Collapses the IA problem the audit named (135 routes, no
front door) without deleting any existing screen.

---

## 5. Design principles this establishes

1. **Structure over decoration.** The system's shape communicates; glow does not.
2. **One warm point.** Exactly one amber element per screen. Everything else is cool.
3. **Colour means state, never brand.** All colour resolves through `--status-*`.
4. **Worst-first.** Never average away a failure.
5. **Every visual has a text equivalent.** No screen is image-only.
6. **Observation surfaces never command.** Read-only is enforced by test, not by habit.
7. **No hex in components.** Tokens or nothing.
