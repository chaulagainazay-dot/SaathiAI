# M17.25 Validation — Project MCP Governance and Memory Consolidation

**Date:** 2026-07-15
**Branch:** `milestone/m7-security-engine`
**Commit message:** `feat(mcp): govern project memory integrations`

## Scope

Governance, configuration, validation, and adapter-boundary work for MCP inventory and codebase-memory consolidation. Continuum **not** installed. No second vector store.

## Environment gate

| Check | Result |
|-------|--------|
| Repository root | `/Users/macbookpro/SaathiAI` |
| Branch | `milestone/m7-security-engine` |
| Starting HEAD | `e64b6b2` (ECP M17.24) |
| Working tree before | clean |
| Sync with origin | 0 ahead / 0 behind |

## Deliverables verified

| Item | Status |
|------|--------|
| `docs/MCP_INVENTORY.md` | present, authoritative |
| `docs/EXTERNAL_CAPABILITY_STATUS.md` | present |
| `saathi/mcp_governance/*` | inventory, namespace, contract, health, policy, redaction, events |
| Canonical id `saathi-codebase-memory` | unique; aliases documented |
| Continuum `BLOCKED_LICENSE` | enforced in inventory + tests |
| Control Center `mcp_health` cell | wired |
| CEO brief on degradation only | wired |
| Critical checks `mcp.*` | six blocking checks |
| Focused tests | `tests/test_m17_25_mcp_governance.py` |

## Manual verification (fake / local harness)

| Step | Expected |
|------|----------|
| Health on FakeMemoryBackend | `status=ok` |
| Search `saathiai` | hits, `consulted=true`, `untrusted=true` |
| Search other namespace | denied / namespace_violation |
| Verified lesson write | ok + Evidence id |
| Disable MCP | degraded search, core continues |
| Re-enable | recovery |

## Trading Guardian

Unchanged and unengaged. Governance package has no trading symbols.

## Rollback

```bash
git revert <m17.25-commit>
# or disable only:
export SAATHI_MCP_CODEBASE_MEMORY_DISABLED=1
```
