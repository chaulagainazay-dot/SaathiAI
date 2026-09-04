# SaathiOS Canonical Unification Ledger

**Status:** IN PROGRESS
**Date:** 2026-09-04
**Canonical product:** SaathiOS
**Intelligence layer:** SaathiAI
**Integration branch:** `integration/saathios-canonical-unification`
**Integration worktree:** `/Users/macbookpro/SaathiOS/apps/saathi-os-canonical-unification`
**Starting baseline:** `milestone/m312-m319-connectivity-governance` at `adb1990bf2dcd6a998e05e8157fbfe9b20fb99d0`
**Canonical local URL:** `http://127.0.0.1:3000`

This ledger records the source, ownership decision, destination, and validation
for every material capability considered during the SaathiOS canonical
unification. A branch being newer does not make it authoritative. Runtime,
security, tests, evidence, resource fit, and existing architecture decide.

## Product boundary

- **SaathiOS** is the only product and application shell.
- **SaathiAI** is the internal intelligence layer: model routing, inference,
  reasoning, memory, and agent intelligence.
- **Saathi** is the user-facing assistant/persona.
- Separate applications in `/Users/macbookpro/SaathiOS/apps` remain separate Git
  repositories and integrate through governed application/connector boundaries.
- No historical branch may introduce a second frontend, execution authority,
  voice capture owner, agent runtime, model router, or trading authority.

## Baseline decision

`adb1990b` is the baseline because it is the live, newest integration tip and
already contains the certified trading program, NEPSE work, Orbit fleet UI,
platform runtime, application shell, and current infrastructure. The
`feature/central-command-core` line is an integration input, not the baseline:
it contains 122 patch-unique commits but is 80 commits behind the chosen tip.

The existing live checkout at `/Users/macbookpro/SaathiAI` is not edited by this
work. Its uncommitted files remain source evidence until explicitly reconciled.

## Feature provenance matrix

| Capability | Existing source | Source SHA | Chosen implementation | Decision | Destination | Validation |
| --- | --- | --- | --- | --- | --- | --- |
| Product/application shell | live milestone branch | `adb1990b` | existing Next.js SaathiOS shell | KEEP | `saathi-os/app`, `saathi-os/components` | pending full frontend/browser gate |
| Central Command composition | live milestone + Command Core | `adb1990b`, `37d48f63` | retain mature hybrid command UI; integrate truthful runtime snapshot and authority surfaces | COMBINE | `saathi-os/app/command`, `saathi-os/lib/command-*`, `saathi-os/components/command` | pending merge and browser gate |
| Root user experience | live milestone | `adb1990b` | make Central Command the explicit primary experience without adding another shell | ADAPT | `saathi-os/app/page.jsx` and shell navigation/metadata | pending browser gate at port 3000 |
| Conversation/chat | live milestone | `adb1990b` | `ConversationService` and existing durable chat boundaries | KEEP | `saathi/platform/conversation`, `saathi/chat`, `saathi-os/components/chat` | pending regression tests |
| Voice session ownership | Command Core hardened voice line | `457f9824` through `37d48f63` | one `VoiceSessionProvider`/input owner and backend voice runtime; retire legacy capture surfaces | INTEGRATE | `saathi-os/lib/voice-session`, `saathi-os/components/voice`, `saathi/platform/voice` | pending capture inventory, security tests, browser gate |
| Live-checkout voice cleanup | uncommitted live checkout | no commit | reconcile four UI removals plus `voice-surface.test.js` after branch merge | ADAPT | shell, OS/chat/mobile surfaces, frontend test | pending comparison and focused tests |
| Condensed voice branch | canonical-v2/recovery line | `c738ac4a` | V-NEXT/R2.1 hardened ownership remains canonical | REJECT | none | rejected to prevent competing microphone/runtime ownership |
| Model routing | live milestone | `adb1990b` | existing `ModelRouter` and governed inference path | KEEP | `saathi/model_router.py`, `saathi/inference` | pending inference regressions |
| Kimi K3 via NVIDIA | Command Core | `37d48f63` | closed, default-off governed provider and qualification harness | INTEGRATE | `saathi/inference` | pending offline tests; no live provider call |
| Local inference/Ollama | live milestone | `adb1990b` | small-model, loopback, no-auto-download policy | KEEP | `saathi/inference`, `saathi/agent_runtime/harness` | pending resource/health audit |
| Agent run runtime | live milestone | `adb1990b` | `saathi.agent_runtime` remains canonical for multi-step runs | KEEP | `saathi/agent_runtime` | pending full regression |
| Platform execution runtime | live milestone | `adb1990b` | `PlatformAgentRuntime` composes agent runs with platform context | KEEP | `saathi/platform/runtime.py` | pending platform tests |
| Agent harness | live milestone/Command Core | `adb1990b`, `37d48f63` | existing bounded proposal-only harness; never external-write authority | ADAPT | `saathi/agent_runtime/harness` | pending authority invariants |
| Platform missions/tasks | live milestone | `adb1990b` | existing durable mission runtime and orchestration | KEEP | `saathi/platform/mission_runtime`, `saathi/platform/orchestration` | pending mission tests |
| ExecutionGateway | live milestone + Command Core hardening | `adb1990b`, `37d48f63` | sole external-action authority with actor propagation and fail-closed authorization | COMBINE | `saathi/execution`, `saathi/tool_runtime` | pending Phase 16-20 authority suites |
| External-write containment | Command Core | `37d48f63` | closed writer registry plus governed grants/delegations | INTEGRATE | execution layer and registered adapters | pending repository-wide containment suite |
| Approvals | live milestone + Command Core | `adb1990b`, `37d48f63` | platform approval records bound to authenticated actor, run, and execution intent | COMBINE | `saathi/platform`, `saathi/agent_runtime`, frontend approval surfaces | pending approval/RBAC tests |
| Authentication/RBAC | live milestone + Command Core | `adb1990b`, `37d48f63` | existing platform identity/RBAC plus actor propagation hardening | COMBINE | platform auth/context and API boundaries | pending auth/security suites |
| Memory | live milestone | `adb1990b` | existing canonical memory engine; keep distinct from evidence | KEEP | `saathi/memory` | pending memory regressions |
| Persistence | live milestone + R2.1 state isolation | `adb1990b`, `457f9824` | canonical state-root abstraction; no checkout-local runtime databases | COMBINE | platform stores and state-root helpers | pending isolation tests |
| Audit/evidence | live milestone + Command Core | `adb1990b`, `37d48f63` | preserve existing audit/evidence authorities; add actor/result sanitization evidence | COMBINE | `saathi/audit`, `saathi/evidence`, `saathi/security` | pending audit/secret gates |
| Market data and portfolio intelligence | live milestone | `adb1990b` | current governed NEPSE/crypto feed, portfolio, research, and attribution line | KEEP | `saathi/platform` trading packages | pending trading regressions |
| Trading Guardian | live milestone | `adb1990b` | existing deterministic guardian and kill switches; paper/advisory defaults | KEEP | `saathi/platform/trading_guardian.py`, `saathi/platform/tg` | pending guardian invariants |
| Trading execution/reconciliation | live milestone | `adb1990b` | existing paper-only OMS/execution integrity/reconciliation; no broker activation | KEEP | `saathi/platform/paper_trading`, execution layer | pending trading program suite |
| Health/diagnostics | live milestone | `adb1990b` | existing infrastructure and connector diagnostics | KEEP | `saathi/infrastructure`, platform health APIs | pending runtime health gate |
| Apps/integrations | live milestone + separate app repos | `adb1990b` + independent SHAs | governed registry/adapters; apps stay isolated repos | KEEP | app launcher/registry/connectors | pending route and application tests |
| Twenty CRM evaluation | evaluation worktree | `2c983194` | preserve branch as isolated read-only experiment | DEFER | no runtime merge | deferred: dependency/resource/ownership decision |
| Historical integration audit | audit worktree | `2d629968` | use findings as provenance, not runtime source | ARCHIVE | referenced by this ledger | documentation-only input |
| Spec-kit files in live checkout | uncommitted live checkout | no commit | development workflow only; not product/runtime | DEFER | none until separately reviewed | preserved in original checkout |
| NEPSE trading-intelligence design exports | uncommitted live checkout | no commit | design evidence, not executable authority | DEFER | none until UX review | preserved in original checkout |
| Separate SaathiOS applications | workspace app repositories | independent SHAs | keep repository identity and integrate through app/connector contracts | KEEP | `/Users/macbookpro/SaathiOS/apps/*` | no merge into core repository |
| TalkingYeti model assets | workspace model directories | independent upstreams | optional external assets, never required for base startup | KEEP | `/Users/macbookpro/SaathiOS/ml-models/talkingyeti` | resource audit only |

## Canonical subsystem ownership

| Responsibility | Canonical owner |
| --- | --- |
| Frontend and product shell | `saathi-os/` |
| Central Command | `/command` composition plus its command read models |
| Conversation | `saathi.platform.conversation.ConversationService` with governed chat adapters |
| Voice | frontend `VoiceSessionProvider`/input owner plus `saathi.platform.voice.runtime` |
| SaathiAI intelligence/inference | `saathi.inference` selected by `saathi.model_router.ModelRouter` |
| Agent runs | `saathi.agent_runtime` |
| Platform missions/orchestration | `saathi.platform.mission_runtime` and `saathi.platform.orchestration` |
| External action authority | `saathi.execution.ExecutionGateway` and `UniversalBoundary` |
| Approvals/RBAC | platform identity/context/RBAC stores plus execution-bound approval checks |
| Trading Guardian | `saathi.platform.trading_guardian` and `saathi.platform.tg` |
| Paper trading/reconciliation | `saathi.platform.paper_trading` |
| Memory | `saathi.memory` |
| Audit/evidence | `saathi.audit`, `saathi.evidence`, and `saathi.security` by record type |
| Persistence | canonical state root and domain stores; no source-checkout runtime writes |
| Health | `saathi.infrastructure` and platform health endpoints |
| Integrations | governed connector/provider registries and application registry |

## Safety invariants

1. Trading remains paper/advisory by default. No broker connection, withdrawal,
   leverage, or live activation is authorized by this unification.
2. Models and agents propose; they do not approve or execute side effects.
3. External writes pass through the ExecutionGateway with authenticated actor,
   scope, risk, approval, and audit evidence.
4. There is one frontend, one voice capture owner, one agent run runtime, one
   model router, and one source of truth per domain responsibility.
5. Runtime state and secrets remain outside Git. No `.env`, credential, database,
   model weight, cache, or browser profile is copied into this worktree.
6. Old worktrees are preserved until certification and a separate cleanup
   approval.

## Validation record

Validation results will be appended here only after commands have actually run.

