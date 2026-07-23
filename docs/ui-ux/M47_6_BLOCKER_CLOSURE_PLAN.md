# M47.6 — Blocker Closure Plan

**Date:** 2026-07-23  
**Baseline HEAD:** `f909d2ee7cd4e6d6c73c819b1f61e7d3b5a8dbd8`  
**PR:** #2 draft

## Blockers

### 1. BFF CORS

| Field | Value |
|---|---|
| Severity | **CRITICAL** |
| Affected routes | All browser→BFF calls from non-default ports (3100, 3110, 3112 cert) |
| Files | `saathi/server.py`, tests |
| Current | Default allowlist: localhost:3000, 127.0.0.1:3000, localhost:8765 only |
| Required | Explicit allowlist; env-aware; fail closed in production; no wildcard credentials |
| Backend dependency | Config env only |
| Authority impact | None (transport) |
| Deep-link risk | None |
| Fix | Expand default **dev** origins for documented ports; production requires `SAATHI_CORS_ORIGINS`; bound methods/headers; tests |
| Validation | pytest CORS unit tests + cert without CORS noise |
| Stop | Production secrets required / wildcard demanded |

### 2. Chat / Copilot parity

| Field | Value |
|---|---|
| Severity | **HIGH** |
| Affected | `/chat`, `/workspace`, `/saathi`, Ask Saathi panel |
| Files | `ChatWorkspace.jsx`, `CopilotPanel.jsx`, chat pages |
| Current | Full ChatWorkspace on /chat; panel is scaffold only |
| Required | Shared transport; consistent auth/errors; compact panel may omit full chrome |
| Fix | Compact mode on ChatWorkspace; embed in CopilotPanel |
| Redirect `/chat` | **No** unless full deep-link parity proven |
| Stop | New conversation platform required |

### 3. Control workflow parity

| Field | Value |
|---|---|
| Severity | **HIGH** |
| Affected | `/control`, `/command`, `/monitoring`, `/approvals` |
| Current | Control is rich M16 surface; Command/Monitoring partial |
| Required | Workflow inventory; no silent loss; deep links preserved |
| Fix | Map workflows; enhance Command links; **KEEP_LEGACY** for /control |
| Redirect `/control` | **No** |

### 4. Business / Finance parity

| Field | Value |
|---|---|
| Severity | **MEDIUM** |
| Affected | `/business`, `/finance` |
| Current | Business compose; Finance thin page |
| Fix | Compose finance into business read-only; **KEEP_FINANCE** if unique |
| Redirect `/finance` | **No** without full read parity |

### 5. Studio dual surface

| Field | Value |
|---|---|
| Severity | **MEDIUM** |
| Affected | `/studio-os`, `/studio`, `/studio/control-room` |
| Current | StudioWorkspace vs AIStudio queue vs control-room |
| Fix | Document KEEP_BOTH_DISTINCT; nav labels clarify |
| Redirect `/studio-os` | **No** |

## Implementation order

CORS → Chat compact → Control matrix + link-ups → Business compose → Studio boundary docs → Final cert → Decision
