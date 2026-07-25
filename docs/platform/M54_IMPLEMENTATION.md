# M54 Implementation — Private-Alpha Operational Readiness

M54 proves the M50–M53 platform can be operated safely through the real
browser-facing private-alpha workflow. It adds an operational readiness layer on
top of the canonical runtime; it does not redesign the runtime, gateway,
approval, RBAC, identity, or binding architecture.

## What M54 adds

| Area | Module / file | Summary |
|---|---|---|
| Operational diagnostics | `saathi/platform/readiness.py` | Bounded, tenant-scoped health snapshot with private-alpha safety labels |
| Evidence export | `saathi/platform/readiness.py` | Fail-closed allowlist export (JSON/CSV) with deterministic manifest, content hash, and audit event |
| Retention policy | `saathi/platform/readiness.py` | Dry-run purge preview, protected records, legal/operator holds, owner/admin-gated |
| Platform API | `saathi/platform/api.py` | `/runtime/diagnostics`, `/runtime/export`, `/runtime/retention/preview`, `/runtime/retention/hold` |
| Isolated cert DB | `saathi/platform/store.py` | `SAATHI_PLATFORM_DB` env override for a disposable certification database |
| Operator UI | `saathi-os/app/platform/page.jsx` | Operational-readiness panel: safety badges, diagnostics counts, export, dry-run retention |
| UI helpers | `saathi-os/lib/platform-ops.js` | Export kinds, attention severity, UI-state descriptors, retention/export gating, safety badges |
| Browser certification | `saathi-os/scripts/m54_browser_cert.mjs` | Managed BFF+UI lifecycle certifying the authenticated operator surface |

## Design principles

- **One redaction authority.** All export/note redaction reuses the M53
  `RuntimeOperationsService._safe_text`; the export layer adds a fail-closed key
  allowlist plus a deep scrub of a forbidden-key denylist.
- **No new subsystems.** Diagnostics, export, and retention are read/analysis
  surfaces over the existing store and runtime operations service.
- **Server owns authority.** Role and tenancy come from the session token; no
  browser-supplied field grants authority. Retention is owner/admin only
  (`ORG_MANAGE`); diagnostics/export require `RUNTIME_READ`; audit export also
  requires `AUDIT_READ`.
- **Purge is dry-run only in M54.** The retention surface classifies eligible vs
  protected records and never deletes operator data.

## Canonical execution path (unchanged)

```
User → Session → Organization → Workspace → Project → Mission
→ PlatformAgentBinding → PlatformExecutionContext → PlatformAgentRuntime
→ Approval validation → ExecutionGateway → ToolExecutionService
→ ToolRegistry → Adapter → Audit
```

`PlatformAgentRuntime` remains canonical; `ExecutionGateway` remains the sole
registered-tool execution authority.
