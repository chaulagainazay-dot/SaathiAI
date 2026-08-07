# CURRENT_SURFACE_INVENTORY — UI-NEXT-1

**Source tip:** `integration/saathios-canonical-baseline` @ `20302574…`  
**Method:** code inspection of `saathi-os/` (not roadmap alone).

## Primary surfaces (pre-composition)

| Surface | Route(s) | Reusable pieces | Notes |
| --- | --- | --- | --- |
| Home | `/` | `useAttentionHome`, attention rows, metrics | Attention spine already strong |
| Command | `/command` | Thin page: overview JSON + attention list | **Target of composition** |
| Chat | `/chat` | VoiceControl, ChatWorkspace | Separate conversation stack |
| Agents | `/agents`, `/platform/agents` | Module routes | Registry-driven |
| Missions | `/missions`, `/platform/missions` | Mission pages | Lifecycle UI |
| Approvals | `/approvals`, `/platform/approvals` | `lib/approvals.js` | Inbox |
| Monitoring | `/monitoring` | Infra health | Legacy `/infrastructure` alias |
| Trading | `/trading/*` | `lib/trading.js` paper overview | Paper only |
| Portfolio (paper) | `/trading/paper-portfolio` etc. | Trading fetchers | |
| Research | `/trading/research*` | TG research UIs | |
| Voice settings | `/settings/voice` | voice-settings lib | |
| Voice enrollment | `/voice` | MediaRecorder legacy | Not command prefs |
| Evidence | `/evidence`, `/platform/evidence` | evidence APIs | |
| Platform ops | `/platform/*` | M50+ identity/ops | |
| Settings | `/settings` | | |

## Existing composition primitives (reuse)

- `StatusBadge`, `AuthorityBadge`, `RiskBadge`, `EvidenceBadge`, `LoadingState`, `EmptyState`, `ErrorState` (`components/ui.jsx`)
- `aggregateAttention` + normalizers (`lib/attention.js`)
- `useAttentionHome` pattern (partial failure isolation)
- `useTradingOverview` / `plat` paper paths (`lib/trading.js`, `platform-client.js`)
- Shell copilot (`openCopilot`) for Ask Saathi
- Global voice docks (`VoiceRuntimeProvider` / `VoiceOutputProvider`) — **not** owned by `/command`

## APIs consumed by command composition

- `GET /api/v1/control/overview`, `/control/attention`
- connectors pending approvals
- missions list, evidence list, infra health
- platform paper accounts/safety/recon (via `plat`)

## Duplication / legacy

| Item | Classification |
| --- | --- |
| Home vs Command attention | COMPOSE (Home keeps attention spine; Command becomes control plane) |
| Legacy `/control` | KEEP / REDIRECT_LATER |
| Legacy `/voice` enrollment | DEPRECATE_LATER |
| Chat VoiceControl vs global runtime | KEEP_SEPARATE until V-NEXT-1 |
| Duplicate approvals routes | KEEP (platform + root) |

## Loading / empty / error

Home already models partial aggregation. Command pre-UI-NEXT-1 dumped JSON. Composition adopts Home-style partial sources.
