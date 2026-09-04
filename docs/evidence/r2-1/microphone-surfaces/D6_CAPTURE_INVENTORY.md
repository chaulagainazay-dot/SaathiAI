# R2.1 D6.0 — production microphone capture inventory (canonical convergence update)

Repeated at `032d0d5` (`validation/r2-1-real-microphone-owner`), clean tree,
before any D6 edit.

## Search performed

Case-sensitive `grep -rnE` over `saathi-os/app`, `saathi-os/components`,
`saathi-os/lib`, `static/`, `client/`, excluding `node_modules`, for:

`getUserMedia`, `SpeechRecognition`, `webkitSpeechRecognition`, `MediaRecorder`,
`AudioContext`, `enumerateDevices`, `navigator.permissions … microphone`,
`useVoice`, `MobileMic`, `sendVoice`, `enrollVoice`, audio upload wrappers,
microphone track handling.

Reachability of the two non-Next surfaces was confirmed against
`saathi/server.py`: `app.mount("/", StaticFiles(directory=ROOT/"client", html=True))`
and `app.mount("/ielts", StaticFiles(directory=…))`.

## Inventory

| # | Surface | Capture API | Ownership | D6 disposition |
|---|---|---|---|---|
| 1 | `lib/voice-session/*` + `VoiceRuntimeProvider` + `VoiceRuntimeDock` | `openMicrophoneForClaim` → `getUserMedia`; one `SpeechRecognition` inside the pipeline; `AudioContext` frame tap on the *same* stream | canonical `AudioInputOwner` claim | keep — canonical, claimed |
| 2 | Former `components/chat/VoiceControl.jsx` (`/chat`) | formerly owned `getUserMedia` + `SpeechRecognition` | retired | removed during canonical convergence; `/chat` uses #1 |
| 3 | `components/MobileMic.jsx`, mounted globally in `Shell.jsx` | own `SpeechRecognition`, no claim | **unclaimed** | D6.1 — delete |
| 4 | `components/mobile/MobileSaathi.jsx` via `lib/useVoice.js` | `getUserMedia` + `MediaRecorder` → `POST /api/v1/voice/command` | **unclaimed** | D6.2 — remove voice portion |
| 5 | `app/os/page.jsx` via `lib/useVoice.js` | same as #4 | **unclaimed** | D6.3 — remove voice portion |
| 6 | `lib/useVoice.js` | `getUserMedia` + `MediaRecorder` + `sendVoice` | **unclaimed** hook | D6.4 — delete after #4/#5 |
| 7 | `app/settings/voice/page.jsx` | `getUserMedia` twice (permission probe + diagnostic recognition test), own `SpeechRecognition` | **unclaimed** | D6.5 — claim with transient ownership |
| 8 | `app/voice/page.jsx` | none — server component, `redirect("/settings/voice")` | n/a | no change |
| 9 | `components/voice/VoiceDiagnosticsPanel.jsx` | none — reads `navigator.permissions` only, never opens a device | n/a | no change |
| 10 | `client/index.html` (legacy static client, served at backend `/`) | `getUserMedia({audio:true})` + `MediaRecorder` → `POST /api/v1/voice/command` | **unclaimed**, and it discards `DEFAULT_MIC_CONSTRAINTS` | **D6 correction** — see below |
| 11 | `static/ielts/speaking-practice.html` (served at backend `/ielts`) | own `SpeechRecognition`, continuous, self-restarting | **unclaimed** | **D6 correction** — see below |

## Corrections to the pre-D6 expectation

Two expectations carried into D6 were wrong and are recorded rather than
relabelled.

**Expected: "legacy static client — no recorder after S6". False.** S6 removed
the *enrollment* recorder from `client/index.html`. Its push-to-talk command
recorder at `toggleMic()`/`processAudio()` survived, still opens the microphone
with a bare `{ audio: true }`, and still uploads a webm blob to
`/api/v1/voice/command`. It is a reachable, unclaimed production capture
surface. Handled in D6.

**New reachable unclaimed capture: `static/ielts/speaking-practice.html`.** Not
in the expected category list. It starts a continuous, self-restarting
`SpeechRecognition` and streams finals over
`/api/v1/ielts/ws/speaking/{student}`. Included in D6 as a found surface.

## Backend audio-processing surfaces (recorded separately — not browser capture)

`POST /api/v1/voice/command` and the URL/audio tool paths accept audio but open
no microphone. They are bounded by the S4/S5 repairs and remain covered by the
backend endpoint security tests. They are not part of the browser microphone
invariant and are not removed by D6, because direct API compatibility and its
security surface still exist.

## Canonical convergence certification

`CENTRAL_COMMAND_VOICE_SURFACE_CONVERGENCE_COMPLETE`

The former route-specific chat recognizer has been removed. All SaathiOS
command, chat, and Copilot voice interaction now uses the shell-mounted
`VoiceRuntimeDock` and its `VoiceSessionManager` pipeline. The voice settings
page retains only explicit, transient diagnostics that borrow the same
`AudioInputOwner` registry. The separately served IELTS lesson remains the
documented non-command exception described above and has no SaathiOS command,
agent, approval, or trading authority.
