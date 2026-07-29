# Autonomous Architecture Decisions

## ADR-VOICE-001 — platform speech extends existing authorities

- Decision: add the canonical provider-neutral speech service under
  `saathi.platform`, backed by `PlatformStore`, platform context/RBAC, audit and
  evidence references. Legacy `voice_os` remains compatibility-only.
- Alternatives: promote the separate VoiceStore/API; let each module call TTS;
  create a standalone voice service and identity layer.
- Evidence: the legacy voice layer has useful provider/segmentation vocabulary but
  lacks organization/workspace isolation and canonical platform authority.
- Consequences: all new assistant and IELTS speech uses one service and API; no
  duplicate RBAC, approval center, event bus, mission runtime or execution gateway.

## ADR-VOICE-002 — certify macOS TTS before VoxCPM

- Decision: certify local macOS `say` first, retain unavailable as fail-closed, and
  expose VoxCPM only as disabled explicit adapters until separately installed and
  resource-certified.
- Alternatives: install VoxCPM2 Python/MPS now; download GGUF weights; use browser
  speech synthesis as the authoritative provider.
- Evidence: the M2 has 8 GB unified memory; upstream reports about 8 GB CUDA VRAM for
  VoxCPM2 and no M2/8 GB benchmark. System TTS needs no model download.
- Consequences: SaathiOS can speak now without cloud traffic or swap risk; VoxCPM
  status remains implemented-but-not-installed, never implied ready.

## ADR-VOICE-003 — cloning is disabled, design metadata is separate

- Decision: reject cloning/reference-audio synthesis by default. Store only bounded
  provider-neutral design metadata and artifact references.
- Alternatives: expose upstream cloning; accept a consent checkbox only.
- Evidence: verified subject rights, audited consent, anti-impersonation checks,
  synthetic labeling and revocation/deletion controls are incomplete.
- Consequences: the Yeti voice is a written synthetic design, never a real-person
  clone. Future cloning activation requires a separate safety milestone.

## ADR-IELTS-001 — SaathiOS platform owns the bounded IELTS module

- Decision: implement IELTSAlert under `saathi.platform` and the existing SaathiOS
  shell, with the platform database, context, RBAC, notifications, evidence
  references, and audit as authorities.
- Alternatives: extend legacy unscoped helpers; import the separate product repo;
  create a parallel service.
- Evidence: M64 makes ModuleRegistry/browser discovery authoritative; legacy IELTS
  helpers use process memory or direct model calls and lack organization/workspace
  isolation; the separate `pielts` repo is out of this repository's change scope.
- Consequences: a small canonical module service and schema are added in place;
  legacy helpers remain compatibility-only and non-authoritative.

## ADR-IELTS-002 — deterministic local feedback is the operational default

- Decision: use a repeatable, criteria-level local practice estimator. Every result
  is labelled `local heuristic result` / `practice estimate` and includes limitations.
  Speaking pronunciation is `not_assessed` without audio analysis.
- Alternatives: reuse legacy provider calls; report scoring unavailable.
- Evidence: no configured provider is required, paid calls are prohibited, and a
  legacy speaking fallback returns an unsupported numeric estimate.
- Consequences: no secret or network dependency; no official score claim; provider
  capability remains false until a separately governed adapter is configured.

## ADR-IELTS-003 — evidence references, not artifact blobs

- Decision: store bounded artifact/evidence references and metadata only.
- Alternatives: store audio/image payloads in SQLite.
- Evidence: platform evidence and audit services already exist and the product
  boundary prohibits raw media in relational fields.
- Consequences: local workflows are complete for metadata and text submissions;
  artifact upload/storage remains a centralized platform concern.

## ADR-IELTS-004 — manual verification is not payment processing

- Decision: payment records capture declared amount/currency/method, transaction and
  evidence references, and a human-only audited review state. No settlement occurs.
- Alternatives: gateway integration or automatic approval.
- Evidence: no provider registration or production authority exists.
- Consequences: owner/admin review is required; self-approval is denied; records are
  explicitly labelled manual verification.

## ADR-IELTS-005 — activate only through the backend module authority

- Decision: enable IELTSAlert in the authenticated ModuleRegistry only after the
  bounded API, permission, tenant-isolation, UI, and browser contracts pass. The
  frontend descriptor remains a non-authoritative metadata mirror.
- Alternatives: keep the module as a placeholder; make frontend routing authoritative.
- Evidence: M64 established backend discovery as browser authority, and M67 verifies
  the complete minimum operational contract.
- Consequences: IELTSAlert is actionable in navigation, dashboard, and command search
  only when returned by backend discovery; registration itself grants no permission.

## ADR-IELTS-006 — unavailable provider is an explicit adapter state

- Decision: compose the local heuristic through `SafeFallbackScorer` with an explicit
  unavailable provider adapter when no governed scorer is configured.
- Alternatives: call legacy provider helpers; invoke the local scorer directly without
  provider-state provenance; return no feedback.
- Evidence: no safe configured provider exists and paid/network provider use is not
  authorized.
- Consequences: provider failure details stay private, local fallback is repeatable
  and visibly labelled, and module capability remains provider-assisted `false`.

## ADR-IELTS-007 — remediate runtime dependencies without framework migration

- Decision: move Next.js to the compatible 15.5.22 patch line and override its
  vulnerable production PostCSS/Sharp transitive versions; update Playwright and
  local PostCSS for the test/build toolchain.
- Alternatives: accept production high-severity advisories; perform an unrelated
  Next/ESLint major migration.
- Evidence: production `npm audit` initially reported three high vulnerabilities;
  the bounded update yields zero production vulnerabilities and passes all frontend,
  build, and browser gates.
- Consequences: runtime audit is clean. ESLint-only minimatch advisories remain
  documented until a coordinated major toolchain upgrade.

## ADR-MISSION-001 — compose mission control over existing platform authorities

- Decision: keep `missions` in `PlatformStore` authoritative, add additive
  mission-runtime tables and a tenant-scoped service, and reserve all external tool
  dispatch for `PlatformAgentRuntime` through the sole `ExecutionGateway`.
- Alternatives: extend the legacy M10 executor directly; create another mission
  database, queue daemon, identity layer, or execution engine.
- Evidence: M17 already proves graph execution concepts, M20 provides engineering
  checkpoint semantics, M52 makes `PlatformAgentRuntime` canonical, and the platform
  store/context/RBAC/audit services already own durable tenant state and authority.
- Consequences: M69 adds no tool execution path. M70 may schedule and coordinate tasks
  but can dispatch them only through the canonical runtime/gateway and cannot infer or
  bypass approval.

## ADR-MISSION-002 — persist an explicit hierarchy and immutable evidence trail

- Decision: model Goal → Phase → Milestone → Task → Subtask as bounded nodes, task
  dependencies as a validated DAG, and evidence/decisions/checkpoints/reviews/
  certifications as append-only mission artifacts.
- Alternatives: store an opaque plan JSON blob; infer progress from logs; overwrite
  checkpoints.
- Evidence: restart recovery requires deterministic task identity, explicit
  transitions, dependency status, budget counters, and a snapshot hash.
- Consequences: plan replacement is allowed only before any task attempt and clears
  stale plan artifacts atomically. Completion is gated by passing named evidence and
  independent review where configured.

## ADR-MISSION-003 — role agents delegate; they never grant or execute

- Decision: represent Planner, Architect, Implementer, Reviewer, Test, Browser,
  Documentation, and Certification agents as a fixed orchestration-role directory.
  A role may submit one declared task only to `PlatformAgentRuntime.execute_context`
  or resume an existing platform execution through the canonical runtime.
- Alternatives: give every role its own executor, connector client, credential set,
  or implicit permission map.
- Evidence: PlatformAgentRuntime already owns identity/binding/session validation,
  approvals, idempotency and runtime state; ExecutionGateway is the sole registered
  tool boundary.
- Consequences: agent selection grants nothing. Runtime binding policy and RBAC can
  deny any role task, approval requirements remain human-controlled, and no
  mission-runtime module imports or invokes ExecutionGateway.

## ADR-MISSION-004 — retry only confirmed failure; never replay uncertainty

- Decision: retry only a small allowlist of transient error codes paired with
  `FAILURE_CONFIRMED`, within each task's retry ceiling and mission resource budget.
  Approval waits resume the original platform execution. Recorded dispatch with
  unknown outcome is blocked for review and never replayed automatically.
- Alternatives: retry every exception; create a fresh execution after approval;
  assume interrupted dispatch failed.
- Evidence: M52 recovery explicitly classifies recorded dispatch as requiring manual
  review, while the gateway's outcome contract distinguishes confirmed failure from
  unknown side effects.
- Consequences: exponential retry backoff is finite; unexpected errors fail closed;
  recovery needs fresh authenticated context and preserves the original idempotency
  and platform execution record.

## ADR-MISSION-005 — backend state drives a read-only Mission Dashboard

- Decision: expose the runtime through the existing authenticated platform router and
  render its tenant-scoped read model in the existing Mission Control shell. The UI
  is observational and contains no direct execution or automatic approval authority.
- Alternatives: infer mission state from browser data; add a separate mission-control
  service/design system; let the client call the gateway.
- Evidence: M69 already owns persisted mission state, M70 owns bounded orchestration,
  and the existing shell/platform client already enforce one identity, workspace,
  navigation, and status vocabulary.
- Consequences: every displayed health/progress/evidence/checkpoint value comes from
  the backend, missing state fails closed, and execution continues only through the
  authenticated orchestrator → PlatformAgentRuntime → ExecutionGateway path.

## ADR-MISSION-006 — certification is an atomic, server-authored terminal transition

- Decision: allow final certification only from a fully completed runtime whose
  tasks, budgets, evidence, independent review, latest checkpoint, commit references,
  browser state, and test state agree. Insert the immutable certificate and transition
  the runtime to `CERTIFIED` in one repository transaction.
- Alternatives: let the UI mark a mission certified; accept a client-provided
  certifier; write a certificate before transitioning state; infer certification
  solely from task completion.
- Evidence: task completion alone does not prove verification, checkpoint freshness,
  evidence ownership, or durable terminality. A split write can leave a certificate
  without a certified runtime, or a certified runtime without a certificate.
- Consequences: certification is tenant-scoped, authenticated, independently reviewed,
  snapshot-hashed, restart-persistent, and immutable. Any mismatch fails closed with
  no partial certificate or state transition.

## ADR-VOICE-004 — centralize speech in one bounded platform service

- Decision: all new platform modules call `SpeechService`, which owns lifecycle,
  queueing, provider selection, persistence, artifact references, cancellation,
  evidence, audit, and restart reconciliation.
- Alternatives: let shell and IELTS call `/usr/bin/say` or VoxCPM directly; extend the
  legacy `VoiceStore` into a second platform authority.
- Evidence: the legacy voice subsystem predates platform RBAC and tenant/workspace
  scope, while `PlatformStore` and `PlatformExecutionContext` already provide the
  required serialized state and authority.
- Consequences: legacy voice input remains compatible but is not authoritative for
  platform output. Heavy-provider concurrency is one, queue depth is eight, text is
  memory-only, and a provider grants no permission.

## ADR-VOICE-005 — certify asynchronous macOS artifacts before model inference

- Decision: certify native macOS AIFF synthesis and authenticated browser playback as
  the lightweight English baseline. Provider-native chunk streaming is not claimed;
  authenticated HTTP range delivery begins after artifact completion.
- Alternatives: install a multi-gigabyte model first; claim CLI `--stream` as an API
  stream; allow automatic local playback.
- Evidence: the warm native artifact path measured 1.663 seconds and about 48 MB
  process maximum RSS, while the VoxCPM2 Python route approaches the entire 8 GB
  machine budget before the application workload.
- Consequences: UI work stays non-blocking and user-controlled. The 4.539-second cold
  artifact result is a declared limitation rather than hidden by an unsupported
  streaming claim.

## ADR-VOICE-006 — VoxCPM remains an explicit out-of-process optional boundary

- Decision: support only explicit GGUF/Metal CLI and loopback-service adapter modes.
  Keep both disabled until an executable/service and model paths are configured;
  never import, start, or download VoxCPM during application startup.
- Alternatives: add VoxCPM/Torch to core dependencies; auto-download weights; run
  inference inside FastAPI; treat adapter presence as runtime integration.
- Evidence: upstream resource/compatibility evidence and local disk/Python/Torch
  inventory show that the full model route is unsafe to certify on M2/8 GB without a
  separately approved resource evaluation.
- Consequences: provider health distinguishes implemented, installed, configured,
  model available, runtime verified, quality reviewed, and certified. VoxCPM is
  currently `CONFIGURED_NOT_INSTALLED`, English is certified only through macOS, and
  Nepali remains unsupported-not-verified.

## ADR-VOICE-007 — disable cloning below the provider boundary

- Decision: profile validation rejects reference artifacts and active cloning consent,
  providers report cloning false, and no cloning or enrollment API is exposed.
- Alternatives: expose dormant cloning fields; rely on a provider flag; enroll
  reference audio before consent/evidence deletion controls exist.
- Evidence: the current platform lacks the complete verified-rights, consent audit,
  synthetic labeling, revocation, deletion, public-figure restriction, and reference
  artifact governance required by the goal.
- Consequences: `voice.clone.request` and `voice.clone.approve` reserve stronger future
  authority but cannot activate cloning. The Yeti profile is written voice-design
  metadata only and never clones a person.

## ADR-VOICE-008 — separate synthesis from explicit browser playback

- Decision: a completed assistant response exposes `Speak` to request synthesis; when
  authenticated audio is ready, a separate user action invokes `Play`.
- Alternatives: autoplay every response; call browser `speechSynthesis`; play
  immediately after an asynchronous synthesis request.
- Evidence: the goal prohibits autoplay, browser gesture policies are inconsistent
  across delayed network work, and browser speech synthesis would bypass the canonical
  provider/evidence/audit layer.
- Consequences: user intent is unambiguous, audio never starts on navigation or data
  refresh, and every platform module can reuse one shell client. The extra Play action
  is a deliberate safety/usability tradeoff and is visibly communicated.

## ADR-VOICE-009 — IELTS speaks feedback, not the learner submission

- Decision: project only the persisted backend feedback, criteria, limitations, and
  non-official label into bounded Yeti-profile speech.
- Alternatives: speak the entire record including the learner response; create an
  IELTS-specific TTS path; use browser speech synthesis.
- Evidence: learner submissions can contain private content unrelated to feedback,
  and a second speech implementation would bypass the canonical audit, cancellation,
  provider health, and artifact controls.
- Consequences: Read aloud is English-only, transparent about limitations, bounded to
  4,000 characters, and routed through the same SpeechService. IELTS scoring and
  pronunciation limitations remain unchanged.

## ADR-VOICE-010 — a partial browser run is a limitation, not a certificate

- Decision: close the provider-neutral/native foundation as
  `VOICE_FOUNDATION_COMPLETE_WITH_LIMITATIONS` while retaining the dedicated M77
  browser result as `FAIL`.
- Alternatives: infer browser success from unit/API/native evidence; exceed the
  browser skill's bounded retry ceiling; call the whole foundation failed despite
  passing backend/native evidence.
- Evidence: the final browser attempt passed 14 hard and 1 accessibility gates and
  issued a speech request, but did not observe the completed client state within
  30 seconds. A separate real-provider API diagnostic completed the same fallback
  request. The M64 production browser regression passed independently.
- Consequences: SaathiOS may truthfully claim local backend English synthesis and an
  implemented deterministic-tested UI, but not certified browser playback,
  browser cancellation, browser IELTS read-aloud, or production readiness.
  Superseded for browser playback by ADR-VOICE-011 / M78.

## ADR-VOICE-011 — certify browser-playable WAV and isolate discovery races

- Decision: default shell synthesis to browser-playable WAV via macOS `say` +
  `afconvert`, keep AIFF supported, single-flight voice discovery without empty-cache
  poison, and run the dedicated voice browser journey before multi-page M64 shell
  regression. Close the foundation as
  `VOICE_FOUNDATION_COMPLETE_WITH_LIMITATIONS` with browser PASS and VoxCPM still
  optional/uninstalled.
- Alternatives: keep AIFF-only artifacts; claim browser success from M77 unit/API
  evidence alone; install VoxCPM to “fix” playback.
- Evidence: M78 isolated three independent failures — Content-Length rewrite hang,
  Chromium AIFF incompatibility, and concurrent `say -v ?` discovery races after M64
  multi-page loads. After the fixes, the managed loopback cert passed 33 hard, 6
  responsive, 2 accessibility, and 4 security gates.
- Consequences: English speech is certified through the authenticated app path on
  macOS. VoxCPM remains uninstalled; Nepali and cloning stay non-certified; production
  is not authorized.

## ADR-VOICE-012 — Real-Time Voice Runtime over SpeechService (M79)

- Decision: implement real-time bidirectional voice as `saathi.platform.voice.runtime`
  (VoiceSessionManager, VoiceInputService, VAD, STT providers, ConversationRuntime,
  SpeechRuntime, AudioPlaybackController) extending M74 SpeechService rather than
  replacing it or promoting M12 `voice_os` to platform authority.
- Decision: browser Web Speech API is the preferred streaming STT path for partial
  transcripts; Whisper-compatible and macOS STT helpers remain optional and never
  auto-install models or packages.
- Decision: barge-in is mandatory — exclusive playback cancel, preserve interrupted
  assistant text, resume LISTENING immediately.
- Decision: microphone capture is client-side only (explicit gesture, loopback, no
  background recording); server owns lifecycle state, RBAC, and transcript persistence
  without raw audio storage.
- Alternatives: full server-side continuous capture; WebSocket-only duplex audio;
  automatic Whisper download; parallel second speech stack.
- Evidence: M79 17 backend tests, 15 M74 regression, 10 frontend voice contracts;
  authenticated `/api/v1/platform/voice/runtime/*` routes; shell Live Voice dock.
- Consequences: SaathiOS can hold interruptible live voice conversations on the
  authenticated path with intentional STT/browser-automation limitations. Production
  remains unauthorized; Trading Guardian unengaged; cloning disabled.

## ADR-VOICE-013 — Live Conversational Intelligence (M80–M86)

- Decision: introduce centralized `saathi.platform.conversation.ConversationService`
  as the sole model path for Live Voice (and reusable by text surfaces). Voice
  Runtime ConversationRuntime fails closed without it; deterministic templates
  are not presented as model intelligence.
- Decision: prefer already-installed local Ollama `qwen2.5:1.5b` on M2/8 GB;
  localhost-only; NDJSON streaming; no auto-download; no paid providers.
- Decision: tool intents are proposed or blocked only; PlatformAgentRuntime and
  ExecutionGateway remain the sole execution authorities.
- Decision: certify browser microphone path with Playwright fake media streams
  (synthetic class) and browser STT partial/final contracts; do not claim human
  microphone verification from automation alone.
- Evidence: M80 tests; M86 live Ollama two-turn + barge-in evidence; M85
  synthetic media cert.
- Consequences: SaathiOS can hold real model-backed interruptible multi-turn
  voice conversations locally. Production remains unauthorized.

## ADR-KNOWLEDGE-001 — Platform Knowledge and Grounding Runtime (M87–M94)

- Decision: implement centralized grounding under `saathi.platform.knowledge`
  and integrate it into `ConversationService` rather than creating a second
  assistant, parallel search authority, or per-module retrieval brains.
- Decision: prefer lexical retrieval with SQLite incremental index on M2/8 GB;
  do not auto-download embedding models; claim semantic only if implemented.
- Decision: enforce source authority hierarchy (runtime/evidence over docs and
  model prior), freshness metadata, tenant/workspace isolation, and treat
  retrieved text as untrusted data that cannot override RBAC, Approval Center,
  ExecutionGateway, or Trading Guardian.
- Decision: keep M19 `saathi.knowledge` multi-repo coordination intact; platform
  knowledge is the Yeti/ConversationService grounding path over approved local
  autonomous state, docs, evidence summaries, and platform records.
- Alternatives: pure model memory; direct frontend index access; embeddings-first
  pipeline; per-domain mini-brains for IELTS/HCG/voice.
- Evidence: `tests/test_m87_knowledge_grounding.py` (22), M80 regressions,
  M93 browser cert, M94 certification summary.
- Consequences: Yeti can answer SaathiOS factual questions with traceable
  citations when sources are indexed. Production remains unauthorized.
