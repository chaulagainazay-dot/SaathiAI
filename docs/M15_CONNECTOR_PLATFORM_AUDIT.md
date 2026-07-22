# M15 Connector Platform Audit

## What shipped (`saathi/connectors/platform/`)
| Module | Role |
|--------|------|
| `models.py` | RiskClass 0–4, MutationClass, ConnState lifecycle + transition validator, ToolDef/ConnectorDef, ToolResult envelope, `normalized_input_hash` |
| `catalog.py` | provider-neutral capability → (category, default risk) |
| `credentials.py` | CredentialRef (metadata only), in-process `resolve_secret`, `has_secret` |
| `adapters.py` | 16 FailureClasses, `is_retryable` (never retries auth/authz/uncertain/non-idempotent), DeterministicAdapter (8 fixtures), real-local fs + git |
| `store.py` | `data/connectors.db`: accounts, cred refs, executions (unique idempotency), approvals (bound to input_hash), webhook dedup, sync checkpoints, rate buckets, failures |
| `registry.py` | seeds 11 connectors / 28 tools with honest integration-status labels |
| `execution.py` | **the sole execution boundary** — gateway-routed, approval-bound, idempotent, rate-limited, failure-classified, secret-redacting |
| `health.py` | honest health (no creds → environment-blocked, never "healthy") |
| `webhook.py` | HMAC signature + freshness window + dedup replay defense |
| `sync.py` | resumable checkpointed sync via the engine |
| `mcp.py` | MCP tools as UNTRUSTED connectors; risk clamped UP; gateway-routed |
| `cli.py` | read-only observability + governed `exec` |

## Safety invariants (all test-enforced)
- No connector bypasses the ExecutionGateway (`provenance.gateway_ref` on every result).
- Risk ≥ 3 requires an approval bound to the exact tool+account+input; single-use; expiring.
- Risk 4 is manual-only.
- Idempotency key replays a completed execution instead of re-running.
- Uncertain side effects and non-idempotent failures never auto-retry.
- Secrets are references only; resolved in-process; redacted from errors.

## Existing integrations (migration, not rebuild)
`saathi/connectors/` (accounts/manager) and `saathi/infrastructure/connectors/`
(drivers/registry) are retained. The M15 platform is a new governed subpackage;
existing imports are untouched. Follow-up: route legacy callers through
`ExecutionEngine`, recording any direct-client use as a bounded transitional
exception (Constitution Art. I).

## Not done / honest gaps
- Live authenticated connector workflows: **unverified** (no creds in env).
- Connector REST API (`/api/v1/connectors/*`) and `/connectors` UI: not shipped.
- Legacy connector migration: documented, not executed.
