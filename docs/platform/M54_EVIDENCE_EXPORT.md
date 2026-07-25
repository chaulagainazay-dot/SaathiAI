# M54 Evidence Export

Bounded, tenant-scoped export for authorized private-alpha operators.
`GET /api/v1/platform/runtime/export?kind=<kind>&format=<json|csv>`.

## Kinds
`execution_summary`, `lifecycle_timeline` (requires `execution_id`), `attention`,
`reconciliation_history`, `binding_metadata`, `approval_references`,
`audit_events` (requires `AUDIT_READ`), `certification_manifest`.

## Manifest
Every export returns a manifest:
schema version (`m54.readiness.v1`), kind, format, scope (org/workspace), record
count, columns, `content_hash` (`sha256:` over canonical JSON — deterministic for
identical data), redaction tag, `production_data: false`, environment
`LOCAL_OR_TEST`.

## Redaction (fail-closed)
1. **Allowlist per kind** — only explicitly listed safe fields are emitted;
   unknown/new fields are dropped by default.
2. **Forbidden-key denylist** — a deep scrub removes any key matching passwords,
   hashes, tokens, invite codes, approval secrets, connector credentials,
   private keys, authorization headers, raw arguments (`arguments_json`), raw
   results (`result_json`), and database paths.
3. **Secret-text redaction** — string values are passed through the M53
   `_safe_text` redactor (Bearer tokens, `sk_/gh*` keys, `password=`/`token=`
   pairs, PEM private keys → `[REDACTED]`).

## Excluded (never exported)
passwords, password hashes, session tokens, raw invite codes, approval secrets,
connector credentials, private keys, authorization headers, raw secret-bearing
arguments, unrestricted tool outputs, internal database paths.

## Audit
Each export emits `readiness.evidence_exported` with the content hash and record
count; no raw payload is written to the audit log.

## Formats
- **JSON** — `records` array plus manifest.
- **CSV** — tabular kinds; nested values are JSON-encoded per cell.
