# SaathiOS Voice Output Foundation — Initial Audit

Date: 2026-07-28  
Milestone: M73  
Repository: `~/SaathiAI`  
Branch: `milestone/m61-backend-workflow-persistence`  
Expected historical baseline: `a4cb5c4d872a3edf048d52b7cd62bf9346703613`  
Recovered voice-goal starting HEAD: `7873586aea6066d9e1d51b1d60f85ca413127907`

## Recovery result

The expected SHA is the certified M68 IELTS closeout, but the branch contains the
subsequently completed M69–M72 Autonomous Mission Runtime. Resetting to the expected
SHA would discard completed work, so the voice goal starts from the recovered HEAD.
The M69–M72 runtime and its final documentation are treated as completed history.

The working tree already contained modified generated evidence under
`docs/evidence/m25`, `docs/evidence/m27`, and `docs/evidence/m28`, plus untracked
`docs/design-spec/`. These are protected pre-existing user changes and are excluded
from every voice commit.

## Audit method

- Read the authoritative project documents, autonomous state, Git state, and recent
  milestone history.
- Used the repository knowledge graph before text search to inventory code,
  call paths, routes, services, and tests.
- Used bounded text search only for literals, configuration, dependency declarations,
  shell/public-listener risks, and non-code files.
- Inspected the protected `docs/design-spec/` tree only by directory listing; no file
  there was modified or staged.
- Inspected the target Mac without installing packages or downloading model weights.
- Reviewed the upstream VoxCPM repository and model metadata without cloning it.

## Existing voice and media inventory

| Finding | Classification | Evidence and disposition |
|---|---|---|
| `saathi/voice_os/tts.py` provider registry with deterministic, macOS `say`, and browser placeholders | ADAPT | Useful behavioral history and test seams, but it is process-global, unscoped, byte-oriented, and not integrated with platform identity/RBAC/audit/evidence. The canonical speech layer will not make this registry authoritative. |
| `saathi/voice_os/store.py` sessions, playback events, interruptions, preferences, latency and provider events | MIGRATE | Good lifecycle vocabulary, but it owns a separate SQLite store and user-only scope. Platform voice state belongs in `PlatformStore` with organization/workspace/owner scope. |
| `saathi/voice_os/bridge.py` conversation/approval bridge | OUT_OF_SCOPE | It handles voice input and legacy agent orchestration. Output speech must not inherit this direct orchestration path. |
| `saathi/voice_os/api.py` `/api/v1/voice/*` session API | MIGRATE | Auth is a simple header identity and does not use canonical platform sessions/RBAC. Existing routes remain compatibility-only; the foundation uses `/api/v1/platform/voice/*`. |
| `saathi/voice_os/segmentation.py` markdown/code/URL-safe speech segmentation | REUSE | The bounded cleaning and segmentation behavior is directly useful. Import through the new service rather than duplicating speech text normalization. |
| `tests/test_voice_os.py` provider honesty, real `say`, lifecycle, interruption, cross-user and raw-audio-retention tests | EXTEND | Preserve legacy coverage and add platform-scoped voice tests. |
| `saathi/infrastructure/conversation/speech/*` STT/TTS/VAD driver abstractions, Whisper and Kokoro | ADAPT | Small driver abstractions prove optional imports. They lack tenant scope, artifacts, audit, queueing, cancellation, and platform authority. Kokoro remains a separate optional generation dependency, not the canonical backend. |
| `saathi/voice.py`, `listener.py`, Faster Whisper, microphone and speaker verification packages | OUT_OF_SCOPE | Input capture/STT is not part of this output foundation. No microphone access or enrollment is authorized. |
| `saathi/tools/mr_yeti_voice.py` OpenAI/gTTS/macOS fallback and Yeti scripts | MIGRATE | Contains provider-specific generation and network fallbacks. The safe reusable requirement is the Yeti voice concept, not its direct calls. |
| `saathi/tools/tts.py` Gemini/Edge/local fallback | OUT_OF_SCOPE | Network-capable content-production TTS must not become the signed-in assistant speech path. |
| `static/ielts/mr-yeti.js` browser speech behavior | MIGRATE | Legacy unscoped browser synthesis is replaced on the certified IELTS surface by the authenticated platform speech service. |
| `saathi/tools/content_studio.py` Talking Yeti composition and media helpers | OUT_OF_SCOPE | Video production is separate from interactive response speech. |
| FFmpeg harness and media verification | REUSE | Existing system FFmpeg is available for independent artifact inspection if needed; no new media execution authority is created. |
| `soundfile` base dependency; optional `kokoro`, `faster-whisper`, `sounddevice`, `resemblyzer` | EXTERNAL | Existing optional packages are not proof that a backend is installed, configured, or certified. |
| no VoxCPM package, configured model path, GGUF binary, worker, or service | MISSING | Implement an optional disabled adapter only. No weights or packages are downloaded in M73. |

## Platform authority inventory

| Authority | Classification | Integration decision |
|---|---|---|
| `PlatformExecutionContext` and `PlatformService.context_from_token` | REUSE | All voice APIs derive authenticated organization/workspace/user context from the platform token. |
| platform role permissions in `saathi/platform/models.py` | EXTEND | Add bounded voice permissions to the existing role map. Registration continues to grant no capability. |
| `PlatformStore` SQLite migrations and tenant-scoped rows | EXTEND | Add voice profiles, operations, transitions, idempotency and artifact metadata to the authoritative platform database. |
| `AuditEvent`/platform audit store | REUSE | Profile changes, synthesis creation, cancellation, failure and artifact access are audited without text/audio/path payloads. |
| existing evidence-reference pattern | REUSE | Persist artifact/evidence references and public metadata, never raw reference audio in relational fields. |
| `PlatformAgentRuntime` | REUSE | It remains the canonical agent runtime. Speech consumes already-approved text and does not become another agent executor. |
| `ExecutionGateway` | REUSE | It remains the sole registered-tool authority. Speech provider execution is an internal bounded media service, not a second general tool gateway; it cannot invoke arbitrary tools. |
| Approval Center | REUSE | Basic local speech is permission-gated and does not need per-utterance approval. Provider administration and any future cloning activation require stronger authority/approval. |
| platform notifications | ADAPT | Voice lifecycle is queryable; notifications are reserved for justified operator failures rather than emitted for every utterance. |
| platform health and module read models | EXTEND | Voice health must report configured, installed, ready, active, fallback and language state separately. |
| ModuleRegistry and unified shell | EXTEND | Add voice controls inside the existing shell; do not create a second design system or module authority. |
| M64 and IELTS browser harnesses | EXTEND | Re-run them and add a voice-specific production-build certificate. |
| `bin/saathi-local` localhost launcher | REUSE | Voice APIs remain behind the existing loopback BFF/backend. No public listener or login-time model startup is added. |

## Frontend surface inventory

| Surface | Classification | Decision |
|---|---|---|
| `saathi-os/lib/platform-client.js` token/context invalidation | REUSE | Add voice calls to the same authenticated client and invalidate/cancel on context change/logout. |
| unified platform shell and Glass Frame tokens | REUSE | Voice status and settings use existing components/tokens. |
| assistant/copilot response surfaces | EXTEND | Provide an explicit Speak action for approved text, never autoplay. |
| `components/ielts/IELTSWorkspace.jsx` feedback view | EXTEND | Add authenticated “Read aloud” using the shared speech control. |
| local browser `speechSynthesis` | ADAPT | It may control playback of authenticated audio, but it is not a truthful provider substitute for backend synthesis. |

## Local runtime and resource observation

- Hardware: Apple Silicon M2, arm64, 8,589,934,592 bytes unified memory.
- Disk: 228 GiB data volume, 73 GiB available at audit time.
- System Python: 3.9.6 and incompatible with VoxCPM's documented minimum.
- Existing project environment: Python 3.12.13, compatible with the documented
  `>=3.10,<3.13` range.
- Existing environment size: approximately 1.6 GiB.
- Existing Torch: 2.12.1, above VoxCPM's stated 2.5 minimum; compatibility with the
  package is unverified and must not be inferred from version alone.
- Existing optional packages: `torch`, `soundfile`, `faster_whisper`, `kokoro`, and
  `transformers` are importable.
- Native executables: `/usr/bin/say` and `/usr/bin/afplay` are present.
- FFmpeg: Homebrew FFmpeg 8.1.1 is present.
- macOS reports installed English voices, including `Daniel` (`en_GB`) and multiple
  `en_US` voices. No Nepali voice is certified by this inventory.

## Security findings

- Legacy TTS helpers include network providers and direct subprocess calls and must
  not be exposed through the canonical API.
- The existing `run_bounded` subprocess helper provides process-group cancellation,
  timeout and output bounds and is the preferred subprocess convention.
- Provider-native objects, exception traces, executable/model absolute paths,
  prompt/reference audio, tokens, and raw text must not cross the public API.
- All configured local executables and model paths require absolute-path validation;
  URLs require loopback-only validation.
- Voice cloning is not safely activatable with the current reference-audio consent,
  revocation, verified-subject and deletion workflow. It remains
  `CAPABILITY_DISABLED`.

## Gap summary

The repository has useful legacy voice primitives, but no canonical platform speech
service. Missing pieces are a platform-scoped provider contract, authoritative
persistence, bounded queue/concurrency, robust cancellation and recovery, artifact
delivery, canonical RBAC/API, frontend controls, and a truthful optional VoxCPM
adapter. The smallest safe path is to extend the platform layer, reuse segmentation,
subprocess, context, RBAC, audit and UI systems, certify macOS system TTS first, and
leave VoxCPM configured-not-installed until a separate resource gate authorizes a
model.
