# SaathiOS voice architecture — as implemented

Determined by reading the source in the repair worktree, then probing the running
application. Nothing here is inferred from documentation.

There are **two distinct voice stacks** in the tree. They are not variants of one
design and they do not share a code path. Certification claims must name which one
they refer to.

---

## Stack 1 — Platform voice runtime (M336–M343 private-alpha path)

This is the stack the private-alpha shell mounts, and the one the audit certifies.

| Concern | Implementation |
|---|---|
| Mounted by | `saathi-os/components/Shell.jsx` → `VoiceOutputProvider` + `VoiceRuntimeProvider` |
| Voice **input** | `window.SpeechRecognition` / `window.webkitSpeechRecognition`, with an explicit `navigator.mediaDevices.getUserMedia({audio:true})` gesture first (`components/voice/VoiceRuntimeProvider.jsx:148`) |
| Input session state | Server-authoritative: `POST /api/v1/platform/voice/runtime/sessions` and `/listen`, `/transcript`, `/interrupt`, `/stop`, `/finish`, `/cancel`, `/permission` |
| Voice **output** | **Server-side TTS.** `POST /api/v1/platform/voice/speech` creates an operation; the client polls `GET /voice/speech/{id}` every 250 ms up to 800 attempts, then fetches `GET /voice/speech/{id}/audio` as a WAV blob and plays it through a detached `new Audio(objectURL)` |
| Output cancellation | `POST /voice/speech/{id}/cancel` plus local teardown (`pause`, `removeAttribute("src")`, `load()`, `revokeObjectURL`) |
| **Not** used | `window.speechSynthesis` is not used anywhere in this stack |

### Verified behaviour

- `speak()` awaits `stop()` before issuing a new synthesis request, so two assistant
  responses cannot play at once.
- Logout / workspace switch fires `PLATFORM_CONTEXT_EVENT`; both providers reset and
  local audio is torn down. The backend also cancels speech operations on logout
  (`saathi/platform/api.py:_cancel_user_speech`, `_clear_user_voice_runtime`).
- Route change now stops audio and releases the microphone — **repaired in this
  mission**, see DEFECT-003 and DEFECT-004. Before the repair neither provider
  unmounted on navigation, so their existing cleanup never ran.
- Disabling the voice preference clears audio and dispatches `CANCELLED`.
- Preference is persisted under `localStorage["saathi_voice_output_v1"]`.

### Classification

| Capability | Classification |
|---|---|
| Microphone permission request / denial / fallback | `IMPLEMENTED_AND_WORKING` |
| Browser speech recognition wiring | `IMPLEMENTED_AND_WORKING` |
| Recognition **accuracy** (English, Nepali, mixed) | `BLOCKED_BY_ENVIRONMENT` — headless Chromium grants no real microphone |
| Server-side TTS synthesis + playback controls | `IMPLEMENTED_AND_WORKING` |
| Stop / interrupt | `IMPLEMENTED_AND_WORKING` |
| Overlapping-speech prevention | `IMPLEMENTED_AND_WORKING` |
| Route-change cleanup | `IMPLEMENTED_AND_WORKING` (repaired) |
| Logout cleanup | `IMPLEMENTED_AND_WORKING` |
| **Audible** quality, Nepali pronunciation, volume | `REQUIRES_HUMAN_AUDIO_VERIFICATION` — see `MANUAL_AUDIO_CHECKLIST.md` |
| True barge-in (duck output while input is live) | `NOT_IMPLEMENTED` in this stack — there is a stop control and a server `/interrupt` endpoint, but no ducking. A stop button is not barge-in and is not claimed as such. |

---

## Stack 2 — Chat VoiceControl (`components/chat/VoiceControl.jsx`)

An older, self-contained component used by the chat surface.

| Concern | Implementation |
|---|---|
| Voice input | `window.SpeechRecognition` / `webkitSpeechRecognition`, continuous, interim results |
| Voice output | `window.speechSynthesis` + `SpeechSynthesisUtterance`, spoken segment by segment |
| Session | `POST /api/v1/voice/sessions`, `/turns`, `/interrupt`, `/end` (legacy non-platform API) |
| Barge-in | **Implemented** — `onresult` calls `stopPlayback()`, which calls `speechSynthesis.cancel()` and reports `stop_latency_ms` to the backend |
| Cleanup | Unmount effect stops recognition and cancels synthesis |

This component *does* implement barge-in in the strict sense: new detected speech
cancels in-flight playback. That claim applies to Stack 2 only.

---

## Environment limitations recorded honestly

Measured in the certification run (real Chromium, `page.evaluate`):

```json
{"speechSynthesis": true, "recognition": true, "mediaDevices": true, "voices": 0}
```

- `voices: 0` — headless Chromium ships **no** speech-synthesis voices. Any claim
  about English or Nepali voice availability, pronunciation or intelligibility is
  therefore **not machine-verifiable here**. Stack 1 does not depend on this (its
  audio comes from the server), but Stack 2 does.
- Headless Chromium grants no real microphone, so no transcription accuracy claim is
  made for either stack.

Resulting voice verdict:

`VOICE_INPUT_BROWSER_PERMISSION_PATH_CERTIFIED_WITH_TRANSCRIPTION_LIMITATION`

Audible output quality remains `OWNER_AUDIO_REVIEW_REQUIRED`.
