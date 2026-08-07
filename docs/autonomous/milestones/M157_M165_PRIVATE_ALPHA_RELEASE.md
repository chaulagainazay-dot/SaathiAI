# M157–M165 — SaathiOS Private Alpha Release and Real-World Operator Validation

Date: 2026-07-29

Terminal verdict: `PRIVATE_ALPHA_READY_WITH_LIMITATIONS`

Browser: `SAATHIOS_PRIVATE_ALPHA_BROWSER_CERT_PASSED`

Release version: `0.1.0-private-alpha.1`

Production authorized: **false**  
Public exposure authorized: **false**

## Milestone map

| Milestone | Scope | Status |
| --- | --- | --- |
| M157 | Release baseline + compatibility matrix | Complete |
| M158 | Install / prepare / first-run | Complete |
| M159 | Lifecycle ownership (saathi-local) | Complete |
| M160 | Config contract + local upgrade fixtures | Complete |
| M161 | Full-system backup/restore + DR drill | Complete |
| M162 | Bounded automation execution (opt-in) | Complete |
| M163 | Synthetic operator validation kit | Complete |
| M164 | Support bundle + incident playbooks | Complete |
| M165 | Private-alpha certification gate | Complete with limitations |

## Architecture

Composition-only release engineering package:

`saathi/platform/private_alpha/` + `bin/saathi-alpha`

Reuses: PlatformStore, Mission Runtime, PlanValidator, ExecutionGateway,
Approval Center, Core OS, M55 release, M57 launcher, ops backup patterns.

Does **not** add a second core runtime, scheduler, monitoring platform,
authentication system, or backup engine.

## Evidence

- Tests: `tests/test_m157_private_alpha.py`
- Frontend: `saathi-os/lib/private-alpha.test.js`
- Browser/runtime: `docs/evidence/m157_m165/browser/M165_BROWSER_CERT.json`
- Gate: `docs/evidence/m157_m165/M165_PRIVATE_ALPHA_CERTIFICATION.json`
- Docs: `docs/PRIVATE_ALPHA_*.md`

## Commands

```bash
bin/saathi-alpha prepare|doctor|init|start|stop|status|open|backup|support-bundle|certify
```
