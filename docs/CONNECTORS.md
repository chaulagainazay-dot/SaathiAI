# Universal Account & Connector Layer (v0.6)

The single seam through which every Mission, Director, and Workflow reaches an
external service. Nothing above calls a provider SDK directly.

```
Mission → Knowledge Graph → Account Manager → Connector Manager → Providers
                                                      ↓
                                          Event Bus → Evidence → Learning → Timeline
```

## Layers

### Account Manager (`saathi/connectors/accounts.py`)
Provider-independent registry. One account (a Gmail login, a YouTube channel, a
Stripe key) can be shared across many Missions; one Mission can use many accounts.
- Fields: id, provider, display_name, email, owner, auth_type, scopes, missions[],
  status, created, last_sync, last_used, token_expiry, refresh_status.
- **Secrets encrypted at rest** (Fernet; key at `~/.saathi/.connector_key`, gitignored).
  The API never returns the secret; the raw DB never holds plaintext.
- `link_mission` / `list(mission=…)` — the many-to-many mapping.

### Connector Manager (`saathi/connectors/manager.py`)
The one entry point: `execute(account_id, "email.send", params, mission=…)`.
- Validates the capability against the provider's category.
- Dispatches to the provider **adapter**; until an adapter is wired it runs in
  **SIMULATED mode** — honest, never fakes a real API call.
- Emits an event (`email.sent`, `youtube.uploaded`, …) onto the Event Bus → Evidence
  → Mission Timeline. Every external action is recorded automatically.
- `register_adapter(provider, adapter)` — how a real integration plugs in later.

### Catalog (`saathi/connectors/catalog.py`)
Providers grouped by category; each category exposes CAPABILITIES (verbs), not APIs.
Directors request a capability, never a provider. ~55 providers mapped (Google suite,
Meta, socials, dev/infra, AI providers, payments, CRM, email infra, productivity).

## Design rules (enforced)
- Mission-first: accounts link to Missions; `overview` shows a Mission's accounts.
- Provider-independent + adapter-isolated: swap a provider = swap an adapter.
- Secure by default: encrypted secrets, never in Git, API never leaks them.
- Event-driven: every action → Event Bus → Evidence → Learning → Timeline.
- Versioned/health: `provider_health()` reports live vs simulated per provider.

## Endpoints
- `GET /connectors/providers` — catalog (whitelisted)
- `GET /connectors/accounts` — accounts (no secrets) + health (whitelisted)
- `POST /connectors/accounts` — register (secret encrypted, token-gated)
- `POST /connectors/accounts/{id}/mission` — link/unlink (token-gated)
- `DELETE /connectors/accounts/{id}` — remove (token-gated)
- `POST /connectors/execute` — run a capability (token-gated)

## Built now vs deferred
BUILT: Account Manager (encrypted, mission-linked), Connector Manager (capability
dispatch + event emission), Catalog (~55 providers), Mission integration, endpoints,
CEO Connectors page. All adapters run SIMULATED.
DEFERRED (per deliverables — add adapter-by-adapter with real OAuth apps/keys):
live OAuth flows, real provider API adapters, Email Workspace, Social Workspace,
Calendar/Drive Workspaces. The interfaces above are the seam they plug into.
