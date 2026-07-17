# External Capability Status (Operational Source of Truth)

**Updated:** 2026-07-17 (M21.3 residual path migration + release-check; cloud providers remain disabled; no new paid credentials)
**Register detail:** `docs/SES/v1.0/SES-000E_REPOSITORY_INDEX.md` Part 6
**MCP detail:** `docs/MCP_INVENTORY.md`

This document is the **concise operational** view. SES-000E remains the full register.

---

## Status legend

`REGISTERED` · `PILOT_APPROVED_GOVERNED_MIGRATION_WRITE` · `BOUNDARY_DEFINED` · `CONFIGURED` · `FOCUSED_TESTED` · `INTEGRATED` · `BLOCKED_LICENSE` · `BROKEN` · `DEFERRED`

---

## Active / product-facing

| Repository or MCP | Status | Version / commit | Licence | Integration type | Adapter | Health check | Tests | Last verified | Owner | Disable method | Replacement candidate | Remaining blockers |
|-------------------|--------|------------------|---------|------------------|---------|--------------|-------|---------------|-------|----------------|----------------------|--------------------|
| **saathi-codebase-memory** (local binary / DeusData-class) | `FOCUSED_TESTED` + governance + **M18.2 index** | local SQLite index + binary; M18.1/M18.2 | Local tool (vendor licence separate) | MCP Server + Adapter | `saathi/mcp_governance` + `CodeMemoryConnector` | `health_snapshot()` | `tests/test_m17_25_mcp_governance.py`, `tests/test_code_memory_connector.py` | 2026-07-15 | SaathiOS Architecture | `SAATHI_MCP_CODEBASE_MEMORY_DISABLED=1` / `set_enabled(False)` | Continuum (blocked) for *shared* eng memory only | Home alias duplicate names; not a second vector store |
| **frontend-gsap** skill | `REGISTERED` (skill) | in-repo skill | MIT (skills text) | Skill | `.grok/skills/frontend-gsap` | skill file presence | `test_m17_24_external_capability_foundation` | 2026-07-15 | Architecture | disable skill list | — | GSAP runtime licence for distribution |
| **saathios-loop-engineering** skill | `REGISTERED` (skill) | in-repo skill | MIT adapted | Skill | `.grok/skills/saathios-loop-engineering` | skill file presence | foundation tests | 2026-07-15 | Architecture | disable skill | — | — |
| **external-integration-audit** | `REGISTERED` | in-repo | SaathiOS | Skill | `.grok/skills/external-integration-audit` | skill file | foundation tests | 2026-07-15 | Architecture | remove skill | — | — |
| **external-service-health** | `REGISTERED` | in-repo | SaathiOS | Skill | `.grok/skills/external-service-health` | skill file | foundation tests | 2026-07-15 | Architecture | remove skill | — | — |
| **InsForge/InsForge** | **`PILOT_APPROVED_GOVERNED_MIGRATION_WRITE`** | adapter M18.3 read + M18.4 migration pilot; upstream ~2.2.x | **Apache-2.0** | Adapter / External Service (product data plane) | `saathi/providers/insforge` | `InsForgeProvider.health()` | `tests/test_m18_3_insforge_provider.py`, `tests/test_m18_4_insforge_migration.py` | 2026-07-15 | Architecture | `SAATHI_INSFORGE_ENABLED` / `SAATHI_INSFORGE_WRITES_ENABLED` default false | Managed Postgres/BaaS for products only | Not production; dual flags + fingerprint approval; no raw MCP; no local Docker by default |

---

## Blocked / deferred external repos

| Repository or MCP | Status | Version / commit | Licence | Integration type | Adapter | Health check | Tests | Last verified | Owner | Disable method | Replacement candidate | Remaining blockers |
|-------------------|--------|------------------|---------|------------------|---------|--------------|-------|---------------|-------|----------------|----------------------|--------------------|
| **pouyahasanamreji/continuum** | **`BLOCKED_LICENSE`** | not cloned | **Unclear / undeclared** | MCP Server (candidate) | none | n/a | n/a | 2026-07-15 | Architecture | do not enable | saathi-codebase-memory (code semantic only; different role) | Clear licence or written permission; namespace pilot; no secrets |
| braedonsaunders/codeflow | REGISTERED | not installed | Unclear | CLI Tool | none | planned | none | 2026-07-15 | Architecture | n/a | — | Licence; path allowlist |
| cobusgreyling/loop-engineering | REGISTERED (skill adapted) | skill only | MIT | Skill | saathios-loop-engineering | skill | foundation | 2026-07-15 | Architecture | disable skill | — | Do not install full CLI by default |
| greensock/gsap-skills | REGISTERED (skill adapted) | skill only | MIT skills | Skill | frontend-gsap | skill | foundation | 2026-07-15 | Architecture | disable skill | — | GSAP library terms |
| tracewayapp/traceway | REGISTERED | — | evaluate | External Service | none | — | — | 2026-07-15 | Architecture | — | OpenObserve | 8 GB Mac suitability |
| VersusControl/versus-incident | REGISTERED | — | evaluate | External Service | none | — | — | 2026-07-15 | Architecture | — | — | Pilot not started |
| gtsteffaniak/filebrowser | REGISTERED | — | evaluate | External Service | none | — | — | 2026-07-15 | Architecture | — | — | ExecutionGateway for ops |
| Leantime/leantime | REGISTERED | — | evaluate | External Service | none | — | — | 2026-07-15 | Architecture | — | — | Optional experiment |
| P3 set (Pixelle, freecut, WebCheck, …) | REGISTERED | — | varies | mixed | none/stubs | — | — | 2026-07-15 | Architecture | — | — | Resource + licence per item |
| Vibe-Trading / FinceptTerminal | REGISTERED research only | — | varies | research UI | **none for live trading** | — | — | 2026-07-15 | Architecture | never enable live trade | Trading Guardian (internal) | **No live trading authorized** |

---

## Session / home MCPs (not product-integrated)

| Name | Status | Notes | Disable |
|------|--------|-------|---------|
| context7 | experimental session | docs lookup | `enabled = false` in `~/.grok/config.toml` |
| headroom | **BROKEN** | binary missing | `enabled = false` |
| agent-browser | experimental | not SaathiOS browser gateway | remove from Claude settings |
| exa (mcporter sample) | unused sample | `config/mcporter.json` | ignore/delete entry |
| hosted GitHub/Gmail/Drive | session OAuth | not ExecutionGateway | disconnect host |

---

## Explicit non-goals (M17.25)

- Do **not** install Continuum
- Do **not** add a second vector store or shared-memory server
- Do **not** replace run ledger / SecurityStore / Evidence / CEO / TG memory
- Trading Guardian remains **unengaged**

---

## How to re-verify

```bash
pytest tests/test_m17_25_mcp_governance.py -q
python -c "from saathi.mcp_governance import continuum_status, health_snapshot; print(continuum_status()); print(health_snapshot())"
```
