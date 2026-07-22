# M18.3 Validation — Governed InsForge Read-Only Pilot

**Date:** 2026-07-15
**Branch:** `milestone/m7-security-engine`
**Starting HEAD:** `cdad7c4` (M18.2)
**Commit message:** `feat(providers): add governed read-only InsForge pilot`

## Implemented

* Governance registration (`EXTERNAL_CAPABILITY_STATUS`, SES-000E note)
* Boundary doc (`M18_3_INSFORGE_PROVIDER_BOUNDARY.md`)
* Package `saathi/providers/insforge/` — config, client, sanitization, provider
* Read-only ops: health, metadata, tables, functions, buckets, sanitized logs
* Disabled by default; allowlist; size/timeout limits; no redirects
* Audit/event/SecurityStore best-effort hooks
* Deterministic mock tests (`tests/test_m18_3_insforge_provider.py`)

## Intentionally unsupported / blocked

* All writes, migrations, deploys, schedules, memory, model gateway, MCP passthrough
* Live InsForge connection (not required for tests)
* Docker install / cloud provisioning

## Security controls

* Endpoint allowlist + blocked prefixes
* SSRF: origin-only base URL, host match, no redirects, scheme allowlist
* Loopback/private hosts require `SAATHI_INSFORGE_ALLOW_LOOPBACK`
* Secret redaction in logs/results/public config
* Credentials never in errors

## Trading Guardian

Package scan + invoke denylist; TG unengaged.

## Resource implications

Zero continuous RAM when disabled. No local InsForge stack started by this milestone.

## Next safe milestone

M18.4 candidate: **governed write pilot** (e.g. single approved migration dry-run or storage list+metadata only) behind ExecutionGateway L3/L4 — only when explicitly authorized.
