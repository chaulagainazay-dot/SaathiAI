# SaathiOS Project MCP Inventory (Authoritative for ECP)

**Date:** 2026-07-15
**Milestone:** ECP M17.24 — External Repository Register & Skills Foundation
**Scope:** Document what exists; do not invent runtime integrations.

---

## Strategy

| Layer | Location | Role |
|-------|----------|------|
| **Project policy** | `SaathiAI/.grok/config.toml` | Project-scoped MCP policy; empty pilots until focused tests exist |
| **User/home agent** | `~/.grok/config.toml`, `~/.claude.json` | Developer-session tools; **not** SaathiOS production runtime |
| **Platform clamp** | `saathi/connectors/platform/mcp.py` | When MCP tools are registered as connectors, risk is clamped untrusted |
| **mcporter sample** | `config/mcporter.json` | Exa remote URL sample — **not** production-wired |

**Rule:** Agent MCP connectivity ≠ SaathiOS product integration.

---

## Home-level / session MCP (documented, not product)

| Name | Purpose | Command or URL | Transport | Project scope | Filesystem scope | Network scope | R/W | Secrets | Health check | Timeout | Retry | Enabled by default | Authoritative or experimental | Last verified | Disable method |
|------|---------|----------------|-----------|---------------|------------------|---------------|-----|---------|--------------|---------|-------|--------------------|-------------------------------|---------------|----------------|
| **codebase-memory** | Local code graph intelligence | `/Users/macbookpro/.local/bin/codebase-memory-mcp` | stdio | User + optional Saathi driver | Indexed projects only (tool-defined) | None (local binary) | Read graph; index writes to its own store | None | Binary presence; Saathi `CodeMemoryConnector.health()` | CLI default ~120s | No auto-retry in driver | User config `enabled = true` | **Authoritative for local code intelligence** when binary present | 2026-07-15 (binary + logs + driver tests) | Set `enabled = false` or remove binary / `CODEBASE_MEMORY_BIN` |
| **codebase-memory-mcp** | **Duplicate** of above | Same binary | stdio | Same | Same | Same | Same | None | Same | Same | Same | Enabled (duplicate) | Experimental alias — **dedupe recommended** | 2026-07-15 | Remove duplicate config entry |
| **context7** | Library documentation lookup | `npx -y @upstash/context7-mcp` | stdio | User agent | N/A | Upstash/Context7 network | Read docs | None in repo | stderr “running on stdio” | npx cold start | n/a | Enabled | Experimental for product; OK for agent docs | 2026-07-15 | `enabled = false` |
| **headroom** | (intended headroom MCP) | `headroom mcp serve` | stdio | User | Unknown | Unknown | Unknown | — | **FAILED** — binary missing | — | — | Config says enabled | **Broken experimental** | 2026-07-15 fail | Set `enabled = false` until installed |
| **agent-browser** | Browser automation MCP | `/opt/homebrew/bin/agent-browser mcp --tools all` | stdio | Claude settings only | Browser | Network | High | Session | Binary path exists | Unknown | Unknown | Claude-only | Experimental; **not** governed browser path | 2026-07-15 path only | Remove from Claude settings |
| **exa** | Web search MCP sample | `https://mcp.exa.ai/mcp` | HTTP | `config/mcporter.json` only | N/A | Remote | Read | Remote API | **None in Saathi** | — | — | File present only | Experimental / unused | 2026-07-15 | Delete or leave unused |
| **Hosted GitHub / Gmail / Drive / tasks** | Agent host connectors | Hosted OAuth | Host | Session | Cloud | Cloud | Varies | Host OAuth | Session-dependent | Host | Host | Session | Experimental; not ExecutionGateway | Session | Disconnect host MCP |

### SaathiOS product driver for codebase-memory

| Field | Value |
|-------|-------|
| Adapter | `saathi/infrastructure/connectors/drivers/code_memory.py` |
| Tests | `tests/test_code_memory_connector.py` |
| Env | `CODEBASE_MEMORY_BIN` optional override |
| Status | **PARTIALLY integrated as infrastructure connector** (not ECP Priority list) |
| Disable | Remove binary → `AUTH_REQUIRED` health; registry still loads inert |

---

## Project MCP (this repo)

| Name | Status |
|------|--------|
| Continuum | **Not configured** — pilot is ECP M17.25 |
| CodeFlow | **Not configured** — adapter pilot ECP M17.26 |
| Trading / shell / home-fs | **Forbidden** |

See `.grok/config.toml` for the empty-pilot policy.

---

## Initially allowed project MCPs (policy)

Allowed **when** a dedicated milestone delivers health + tests + disable:

- codebase-memory
- Continuum pilot (engineering knowledge only)
- documentation lookup
- GitHub **read-only**
- filesystem **restricted to SaathiAI**
- Git read-only or controlled
- browser **only** via ExecutionGateway (not raw agent-browser)

---

## Resource note (foundation milestone)

No new MCP process started by this milestone. Home codebase-memory may already run under agent sessions (`ON_DEMAND` / session-scoped). Documented idle measurement for foundation work only (docs/skills): see ECP validation report.
