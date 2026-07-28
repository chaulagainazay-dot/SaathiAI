# M74 — Provider-Neutral Speech Backend

## Result

`COMPLETE`

M74 extends the existing platform authority and serialized `PlatformStore` with
one canonical `SpeechService`. It does not create another authentication,
permission, audit, execution, approval, evidence, or notification authority.

## Delivered

- Canonical provider-neutral request, result, lifecycle, health, capability, and
  voice-profile contracts.
- Durable tenant/workspace/user-scoped speech operations with optimistic
  transitions, idempotency, restart reconciliation, evidence, and audit.
- Bounded priority queue (depth eight), two lightweight workers, concurrency one
  for heavy providers, no retry loop, provider timeouts, cancellation, 32 MiB
  output limit, and 24-hour default retention.
- `MacOSSystemSpeechProvider` using the native local speech executable through
  the existing safe subprocess controller.
- Optional out-of-process `VoxCPMSpeechProvider` for explicit GGUF/Metal or
  loopback-service configurations. It performs no imports, starts, downloads, or
  paid calls.
- Truthful `UnavailableSpeechProvider`.
- Provider-neutral built-in SaathiOS and Yeti Teacher profiles; cloning and
  reference-audio enrollment remain disabled.
- Central platform permissions for read, speak, profile/provider management,
  reference submission, clone request/approval, and audit access. Basic speech
  is a signed-in role capability; registration alone creates no membership,
  session, or permission.
- Authenticated provider, health, profile, operation, cancellation, evidence,
  and range-capable audio APIs.

## Reused architecture

- `PlatformExecutionContext` for identity, RBAC, tenant, and workspace scope.
- `PlatformStore` serialized SQLite authority and platform audit events.
- Existing evidence-link conventions with opaque artifact identifiers.
- Existing `run_bounded` subprocess controller for shell-free process-group
  timeout and cancellation.
- Existing `voice_render` text sanitation.
- Existing FastAPI token and safe-error conventions.

Basic local speech is authorized directly by `voice.speak`, consistent with the
approved goal. Provider management and cloning permissions are stronger, but no
provider-mutation or cloning endpoint exists in this milestone. Because speech
does not execute a general tool, the service does not bypass or duplicate
`ExecutionGateway`; future agent tools must call `SpeechService`, not a provider.

## Lifecycle and privacy

The canonical states are `queued`, `preparing`, `synthesizing`, `streaming`,
`playing`, `completed`, `cancelled`, `failed`, `unavailable`, and `expired`.
This backend certifies asynchronous artifact synthesis; provider chunk streaming
and server-owned playback are not claimed. Browser playback state is a client
concern added in M75.

Raw speech text is not persisted in SQLite, audit, or evidence. Provider-native
objects and absolute paths are not returned. Audio requires the same active
session and ownership/scope checks as operation inspection and is sent with
private, no-store cache headers.

## Provider status

| Provider | Implemented | Installed | Configured | Runtime verified | Certified |
|---|---:|---:|---:|---:|---:|
| macOS system speech | yes | yes | yes | yes | English/local artifact |
| VoxCPM GGUF/Metal | yes | no | no | no | no |
| VoxCPM loopback service | yes | no | no | no | no |
| unavailable | yes | n/a | yes | yes | truthful no-speech |

The VoxCPM adapter is an integration boundary, not a claim that VoxCPM inference
works on this machine.

## Local measurements

The real native provider synthesized the fixed English phrase “Saathi O S local
English voice certification.” to a temporary AIFF and deleted it after the
measurement.

- 184 installed voices reported.
- AIFF: 22,050 Hz, 3.301 seconds, 149,684 bytes.
- Cold artifact ready: 4,539.20 ms, real-time factor 1.375.
- Warm artifact ready: 1,663.31 ms, real-time factor 0.504.
- Measurement-process maximum resident size: 48,332,800 bytes.
- Confirmed real-process cancellation: 46.04 ms; partial artifact removed.
- No swaps observed by the measurement process.

The warm path meets the suggested two-second target. The cold path does not and
is retained as an explicit limitation. The UI remains asynchronous in either
case.

## Verification

```text
.venv/bin/pytest -q tests/test_m74_voice_foundation.py tests/test_m74_voice_api.py
14 passed

.venv/bin/python -m py_compile saathi/platform/api.py saathi/platform/models.py \
  saathi/platform/store.py saathi/platform/service.py saathi/platform/voice/*.py
passed

git diff --check
passed
```

Focused coverage includes validation, lifecycle, idempotency, cancellation,
timeout, failure mapping, unavailable state, system fallback, VoxCPM fakes,
tenant/workspace/owner isolation, RBAC, revoked sessions, input and queue bounds,
heavy concurrency one, authenticated artifact range access, safe 404, health,
audit/evidence, registration without authority, Yeti metadata, and cloning
disabled.

Evidence: `docs/evidence/m74/VOICE_BACKEND_CERTIFICATION.json`.

## Remaining work

M75 adds the shell controls and playback state. M76 integrates IELTS feedback
read-aloud. M77 runs browser, resource, security, and full-repository
certification.
