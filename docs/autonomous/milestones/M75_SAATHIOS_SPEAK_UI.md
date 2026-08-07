# M75 — SaathiOS Speak UI

## Result

`COMPLETE`

The unified shell now owns one shared speech-output client. Persisted assistant
responses in the full Chat workspace and compact Ask Saathi copilot expose a
`Speak` action. Synthesis never starts automatically, and synthesis completion
does not autoplay. The user explicitly chooses `Play` after the authenticated
artifact is ready.

## Delivered

- One `VoiceOutputProvider` shared by the existing shell tree.
- Authenticated provider health, provider list, profile list, speech creation,
  polling, cancellation, and binary audio retrieval through the platform voice
  namespace.
- One global speech dock with enable/disable, provider state, fallback label,
  profile selection, accessible rate control, Play, Stop speaking, retry, and
  live lifecycle status.
- Assistant-only Speak actions; user messages and incomplete/error streams are
  not sent to speech.
- Explicit representation of idle, queued, preparing, synthesizing, streaming,
  playing, completed, cancelled, failed, unavailable, and expired states.
- Bounded 250 ms polling with a 200-second client ceiling and abort on component
  teardown, logout, tenant change, or workspace change.
- Audio object URL revocation and local playback teardown after stop, context
  invalidation, logout, and unmount.
- Server-side cancellation of active user speech before logout or workspace
  session rotation.
- Versioned local preferences containing only enabled state, profile ID, and
  bounded speaking rate. Tokens, text, provider paths, and audio are never
  persisted in browser storage.
- Desktop, tablet/mobile, visible-focus, live-region, keyboard, and
  reduced-motion styling using the existing shell design vocabulary.

## Architecture reused

- Existing `Shell`, Chat workspace, Ask Saathi copilot, platform token client,
  platform context-change event, and global CSS tokens.
- Canonical M74 `SpeechService` and scoped APIs; the browser never calls
  `/usr/bin/say` or VoxCPM directly.
- Existing browser audio element behavior only after a user-controlled Play
  action.

The React best-practices review led to a single shared provider, parallel
metadata requests, versioned minimal local storage, stable callbacks, abortable
global/context lifecycle work, and deterministic cleanup rather than
per-message polling or duplicate listeners.

## No-autoplay contract

`Speak` means “synthesize this approved completed response.” Once the artifact
is authenticated and loaded, the dock says it is ready. Only `Play` invokes
`HTMLAudioElement.play()`. This two-step contract is intentionally more
conservative than browser autoplay heuristics.

## Verification

```text
npm test
188 passed

npm run lint
passed with zero warnings

npm run build
compiled, lint/type validity, and 82 static routes passed

.venv/bin/pytest -q tests/test_m74_voice_foundation.py tests/test_m74_voice_api.py
15 passed

.venv/bin/python -m py_compile saathi/platform/api.py
passed
```

Frontend tests cover authenticated API paths, normalized safe state, loading,
synthesizing, playing, completed, cancelled, failed, unavailable, fallback
metadata, selector/rate controls, no autoplay, semantic controls, context
invalidation, and storage bounds. Backend coverage additionally proves logout
cancels active synthesis before revoking the session.

Evidence: `docs/evidence/m75/VOICE_SHELL_CERTIFICATION.json`.

## Remaining work

M76 adds IELTS feedback read-aloud through this same provider. M77 performs live
desktop/tablet/mobile voice browser certification and full repository,
dependency, secret, localhost, and resource gates.
