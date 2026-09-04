# SaathiOS — Central Command

This Next.js application is the single SaathiOS product shell. The root route
(`/`) is Central Command; the earlier attention dashboard remains available at
`/home`. The compatibility route `/command` renders the same Command Center
component and does not create a second frontend.

## Run

From the repository root, prefer the canonical process manager:

```bash
./bin/saathi-local start
# http://127.0.0.1:3000
```

For frontend-only development:

```bash
cd saathi-os
npm install
NEXT_PUBLIC_SAATHI_API=http://127.0.0.1:8765 \
NEXT_PUBLIC_LOCAL_API=http://127.0.0.1:8765 \
npm run dev
```

Production build validation is `npm run build`; the frontend suite is
`npm test`; lint is `npm run lint`.

## Product boundaries

- SaathiOS is the product and shell.
- SaathiAI is the internal model, reasoning, memory, and agent intelligence.
- Saathi is the assistant/persona.
- `VoiceRuntimeDock` is the one shell-mounted command voice surface.
- Models and frontend controls do not bypass approvals, RBAC,
  `ExecutionGateway`, or Trading Guardian.
- Trading views are paper/advisory unless separately certified in a future
  milestone.

The canonical architecture and merge provenance are recorded in
`../docs/architecture/SAATHIOS_CANONICAL_UNIFICATION.md`.
