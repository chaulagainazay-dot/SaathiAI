# M17.18.1 — Validation & Completion Report

## Scope delivered

Split project memory into two authoritative layers so nightly auto-learning
cannot dirty the curated, git-tracked conventions baseline:

| Layer | Path | Mutated by |
|-------|------|------------|
| Curated baseline | `saathi/memory/conventions.md` (+ other `saathi/memory/*.md`) | Human review only |
| Runtime learning | `data/memory/learned_conventions.md` + `.jsonl` | `memory_reflector` only |

Agent load path: curated files first, then a short learned-conventions slice
(when present). Promotion from learned → curated remains a human review step.

Also gitignores local runtime dirt that repeatedly contaminated the tree:

- `.saathi-agent-state/`
- `storage/*.db` (+ WAL/SHM)

## Files changed

- `saathi/config.py` — `LEARNED_MEMORY_DIR`, `LEARNED_CONVENTIONS_MD`, `LEARNED_CONVENTIONS_JSONL`
- `saathi/scheduler.py` — `memory_reflector` writes learned paths only
- `saathi/agent.py` — `_load_memory()` includes learned slice
- `saathi/memory/MEMORY.md` — documents the two-layer model
- `.gitignore` — agent state + storage runtime DBs
- `tests/test_memory_conventions_split.py` — 3 deterministic tests

## Test results

- **Focused M17.18.1:** 3 passed (`tests/test_memory_conventions_split.py`).
- Trading Guardian: unengaged (memory hygiene only; no trading surface).

## Architecture reused

No second memory engine. Existing `memory_reflector` job + `_load_memory()`
paths; only the write target and load composition changed. `data/` was already
gitignored; learned files live under that tree.

## Remaining / deferred

- Human promotion workflow (CLI/UI) for learned → curated remains manual
- Historical auto-learned lines already in `conventions.md` (if any) are not
  auto-migrated — review/edit as a separate hygiene pass if needed
- Full suite not required for this hygiene slice (targeted validation only)
