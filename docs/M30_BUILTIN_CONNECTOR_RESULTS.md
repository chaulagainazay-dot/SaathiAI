# M30 — Built-in Connector Results

All four M29 built-ins assessed via credential-free sandbox.

| Connector | State | Limitations | Evidence |
|-----------|-------|-------------|---------|
| `gov.http` | CERTIFIED_WITH_LIMITATIONS | fake_transport_only; no_public_internet; sandbox_not_live_provider | `docs/evidence/m30/connectors/gov.http/` |
| `gov.mcp` | CERTIFIED_WITH_LIMITATIONS | policy_inventory_only; no_external_mcp_server; sandbox_not_live_provider | `docs/evidence/m30/connectors/gov.mcp/` |
| `gov.browser` | CERTIFIED_WITH_LIMITATIONS | dry_run_navigate; no_live_login; fake_session_path; sandbox_not_live_provider | `docs/evidence/m30/connectors/gov.browser/` |
| `gov.local_tool` | CERTIFIED_WITH_LIMITATIONS | allowlisted_ops_only; no_arbitrary_os_tools; sandbox_not_live_provider | `docs/evidence/m30/connectors/gov.local_tool/` |

## Readiness implication

* Sandbox certification ≠ live-provider certification.
* Default connector rollout remains **OFF**.
* ACTIVE still requires production certification, readiness, policy, and approval.
* CERTIFIED_WITH_LIMITATIONS does not authorize broader domains or live OAuth.

## Fingerprints

Stored in each package's `fingerprint.json` and the registry
`docs/evidence/m30/certification_registry.json`.
