# M18.2 Validation — Governed Codebase Memory Indexing and Retrieval

**Date:** 2026-07-15
**Branch:** `milestone/m7-security-engine`
**Start HEAD:** `2223322` (M18.1 governance)
**Commit message:** `M18.2 operationalize governed codebase memory`

## Renumbering

| Historical | Canonical |
|------------|-----------|
| M17.25 Project MCP Governance… | **M18.1** |

Git history not rewritten. Browser M17.25 unchanged.

## Delivered

| Area | Evidence |
|------|----------|
| Audit | `docs/M18_2_CODEBASE_MEMORY_AUDIT.md` |
| Identity | `saathi/codebase_memory/identity.py` |
| Indexer | incremental SQLite, secret-safe |
| Retrieval | hybrid lexical/symbol + optional local embed |
| Freshness | CURRENT_WORKTREE / STALE_INDEX / DELETED_SOURCE |
| CLI | `python -m saathi.codebase_memory {health,index,search,...}` |
| Tools | `dispatch_tool(codebase_memory_*)` |
| Eval | `eval_set.py` (repo-grounded) |
| Continuum | BLOCKED_LICENSE |
| Trading Guardian | unengaged |

## Disable

```bash
export SAATHI_MCP_CODEBASE_MEMORY_DISABLED=1
```

## Rollback

```bash
git revert <m18.2-commit>
```
