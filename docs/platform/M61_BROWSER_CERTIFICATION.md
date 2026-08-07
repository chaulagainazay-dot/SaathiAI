# M61 — Browser / Persistence Certification

Harness: `saathi-os/scripts/m61_browser_cert.mjs` (`npm run cert:m61:build`
production; `npm run cert:m61` dev). Isolated 127.0.0.1 BFF + real seed.

Two layers: (1) API contract gates — plan persist + reload + 409 concurrency,
notification persist+dedupe, saved-view persist + secret-rejection (400), template
persist, draft persist, attention mutation + audit, server search, tenant isolation,
unauthenticated→401; (2) browser gates — a **fresh** browser context (no seeded
localStorage) renders the server-persisted saved view and server search results,
proving the data lives on the server, not the client.

Also: `pytest tests/test_m61_workflow_persistence.py` — 11 backend tests (service +
HTTP contract + concurrency + RBAC + tenant isolation + audit).

Full gate results: `m61_evidence/m61_browser_cert.json`.
