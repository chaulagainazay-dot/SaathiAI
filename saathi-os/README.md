# SaathiOS — Sovereign Orbit

The canonical SaathiOS interface, implemented from the *Sovereign Orbit* design language.
Next.js 15 · React 19 · Tailwind CSS 4 · Framer Motion. You are the center; the AI is invisible.

## Run

```bash
cd ~/SaathiAI/saathi-os
npm install      # once
npm run dev      # → http://localhost:3000
```

Production: `npm run build && npm start`.

## The four layers (per the approved flow)

| Route         | Layer                | What it answers |
|---------------|----------------------|-----------------|
| `/`           | **CEO Home**         | "What should I do next?" — priority score, dream progress, top-3 actions, approvals, Saathi briefing |
| `/mission`    | **Mission Control**  | System health & relationships — the living universe of departments |
| `/finance`    | **Finance Workspace**| Deep work — portfolio, equity curve, KPIs, L4-governed approvals |
| `/knowledge`  | **Knowledge Graph**  | Understanding — infinite typed-node graph |
| `/[dept]`     | Generic workspace    | Studio, Learning, Travel, Cafeteria, Crypto, Discovery, Opportunity, Memory, Business |

## Interactions

- **Floating dock** (bottom) — department navigation, auto-highlights the active screen.
- **⌘K / Ctrl-K** — command palette (search commands, departments, actions).
- **Space** — CEO Mode: everything disappears, one decision (Approve / Reject / Ask Saathi).
- **Esc** — dismiss palette / CEO Mode.

## Design system

- **Color = jurisdiction** — every department owns one hue forever (`lib/departments.js`).
- **Glassmorphism** — `.glass` panels, soft blur, department glow.
- **Motion** — 200–300ms flows, animated counters, entrance springs, dashed live-flow edges.
- Tokens live in `app/globals.css`; mock data in `lib/data.js`.

## Wiring to the backend (next milestone)

All screens read from `lib/data.js`. Swap those for `fetch()` calls to the FastAPI app
(`saathi.server`, port 8765) exposing the M1–M5 capabilities — Financial Mission Control's
`to_dict()`, the Executive briefing, portfolio/research/journal endpoints — and the interface
becomes live. No component changes required beyond the data layer.
