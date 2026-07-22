# Baadar Project Memory

The **project brain** for Baadar / SaathiAI. Auto-loaded into every session.
Sub-files below — open them when relevant.

## Curated baseline (git-tracked under `saathi/memory/`)

- [overview.md](overview.md) — what Baadar is, its shape, current state
- [integrations.md](integrations.md) — APIs, tools, credentials, channels connected
- [conventions.md](conventions.md) — **reviewed** patterns, content rules, language, do/don't
- [decisions.md](decisions.md) — architectural and product decisions worth not re-debating

Edit these only after review. They are the authoritative conventions baseline.

## Runtime learning state (gitignored under `data/memory/`)

- `data/memory/learned_conventions.md` — nightly auto-learned bullet sections
- `data/memory/learned_conventions.jsonl` — same notes as append-only JSON lines

Written by the memory-reflector (`scheduler.py` `memory_reflector` job).
**Never write auto-learned notes into `conventions.md`.** Promote durable patterns
from learned files into `conventions.md` only after human review.

The agent loads curated files first, then appends a short learned-conventions
slice (most recent 400 chars when the learned file is large).
