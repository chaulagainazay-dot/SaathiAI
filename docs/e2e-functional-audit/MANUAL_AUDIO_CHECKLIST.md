# Owner audio review checklist — `OWNER_AUDIO_REVIEW_REQUIRED`

Automation cannot judge whether speech is audible, intelligible or correctly
pronounced, and the certification environment (headless Chromium) reports zero
installed speech-synthesis voices. Nothing below has been marked passed by any
automated run. It stays `OWNER_AUDIO_REVIEW_REQUIRED` until a human completes it.

## Setup

1. Start the backend and frontend from the **same** worktree (see
   `RECOVERY_BASELINE.json`, DEFECT-ENV-001 — this is exactly what was wrong before).
2. Open SaathiOS in a normal, non-headless Chromium browser with working audio.
3. Sign in with a private-alpha account. Enable voice output.

## Checklist

| # | Check | Expected | Result |
|---|---|---|---|
| 1 | English assistant response is spoken | Audible and understandable | ☐ |
| 2 | Nepali (Devanagari) response | Either audible Nepali, or a clearly-signalled fallback — a silent failure is a defect | ☐ |
| 3 | Mixed Nepali/English response | Both parts intelligible; no truncation at the language switch | ☐ |
| 4 | Speaking volume | Comfortable at normal system volume | ☐ |
| 5 | Stop control | Audio stops **immediately**, not at the end of the sentence | ☐ |
| 6 | New response while old audio plays | Old audio stops; only one voice is ever heard | ☐ |
| 7 | Navigate to another route mid-speech | Audio stops (repaired as DEFECT-003 — confirm audibly) | ☐ |
| 8 | Log out mid-speech | Audio stops and does not resume | ☐ |
| 9 | Markdown / code in a response | Syntax is not read aloud character by character | ☐ |
| 10 | URLs in a response | Pronounced tolerably, not letter by letter | ☐ |
| 11 | Long paragraph | Plays to the end without stalling or looping | ☐ |
| 12 | Microphone permission prompt | The explanation makes clear why the mic is needed | ☐ |
| 13 | Deny microphone permission | A clear message appears **and text input still works** | ☐ |
| 14 | Speak English, check transcript | Close enough for alpha use | ☐ |
| 15 | Speak Nepali, check transcript | Record what actually happens — do not assume it works | ☐ |
| 16 | Start speaking while assistant is talking | Chat `VoiceControl` should cut playback (barge-in). The platform voice runtime is **not** expected to duck — that is `NOT_IMPLEMENTED` there. Confirm which surface you tested. | ☐ |
| 17 | Navigate away while the mic is live | Recording stops, browser mic indicator goes out (DEFECT-004) | ☐ |
| 18 | Persona | Name and avatar are consistent, no placeholder or stale persona name | ☐ |

## Sign-off

- Reviewer: ______________________
- Date: ______________________
- Browser and OS: ______________________
- Voices available (`speechSynthesis.getVoices().length`): ______
- Verdict: ☐ accepted for private alpha  ☐ defects raised (list ids): ______________

Until this is signed, the mission verdict retains `OWNER_AUDIO_REVIEW_REQUIRED`.
