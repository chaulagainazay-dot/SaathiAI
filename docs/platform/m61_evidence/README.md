# M61 Evidence

Bounded, test-only. No credentials/tokens/keys/secret logs.

- `m61_browser_cert.json` — API contract + fresh-browser persistence cert report.
- `screenshots/` — server-persisted saved view, notifications, server search (fresh browser).

## API matrix / gap matrix
See `docs/platform/M61_FINAL_REPORT.md` §3 and `M61_OPERATOR_WORKFLOW_ARCHITECTURE`
(capability matrix in `lib/operator.js`).

## Reproduce
```
.venv/bin/python -m pytest tests/test_m61_workflow_persistence.py -q
cd saathi-os && npm test && npm run cert:m61:build
```
Limitations: `docs/platform/M61_LIMITATIONS.md`.
