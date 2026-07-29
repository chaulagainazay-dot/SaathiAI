# SaathiOS Private Alpha Release

**Release version:** `0.1.0-private-alpha.1`  
**Channel:** private-alpha  
**Production authorized:** **false**  
**Public exposure authorized:** **false**

## Purpose

Certify that completed SaathiOS Core can be installed, started, operated, backed
up, restored, diagnosed, and used for bounded HCG and IELTSAlert workflows on a
single local Mac — without public exposure or production activation.

## Primary supported machine

| Attribute | Value |
| --- | --- |
| CPU | Apple Silicon (arm64) |
| OS | macOS |
| RAM | 8 GB recommended |
| Storage | 256 GB class, ≥5 GB free headroom |
| Network | localhost-only (`127.0.0.1` / `localhost`) |

Broader compatibility is **not claimed** without evidence.

## Operator entry points

```bash
bin/saathi-alpha prepare
bin/saathi-alpha doctor
bin/saathi-alpha init --ack-local-only
bin/saathi-alpha start          # delegates to bin/saathi-local
bin/saathi-alpha open
bin/saathi-alpha backup
bin/saathi-alpha support-bundle
bin/saathi-alpha certify
```

Lifecycle ownership remains with `bin/saathi-local` (PID + command signature;
never kills unrelated processes).

## Architecture reused

- PlatformStore, ExecutionGateway, Approval Center, Mission Runtime
- M55 release health/metrics/backup validation
- M57 localhost launcher
- M148–M156 Core OS composition
- `saathi.ops.backup` patterns for secret-free archives

## Explicit non-authorization

- Not production-ready
- Not public SaaS
- No live payments
- No production Firebase
- No paid AI provider activation in first-run
- Trading Guardian unchanged / unengaged
- Automations disabled by default

See also: `PRIVATE_ALPHA_INSTALL.md`, `PRIVATE_ALPHA_OPERATIONS.md`,
`PRIVATE_ALPHA_LIMITATIONS.md`, `PRIVATE_ALPHA_CERTIFICATION.md`.
