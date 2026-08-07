# M78 — Voice Browser Re-Certification and Playback Hardening

Date: 2026-07-28

Verdict: `M78_COMPLETE`

## Outcome

M78 closes the M77 browser-certification limitation for the Voice Output Foundation.

SaathiOS now produces and plays real local English speech through the certified
authenticated application path:

1. Speak on approved assistant text;
2. native macOS synthesis with VoxCPM explicit-request fallback;
3. browser-playable WAV artifact delivery;
4. explicit Play (no autoplay);
5. Stop/cancel;
6. IELTS feedback read-aloud;
7. unavailable/fallback surfaces;
8. desktop/tablet/mobile and logout cleanup.

## Root causes fixed

1. **Browser-cert harness Content-Length hang** — rewriting `provider: auto` to
   `provider: voxcpm` reused the original `Content-Length`, which could hang the
   POST. The harness now strips inherited content-length headers.
2. **AIFF not Chromium-playable** — the shell now requests WAV; the macOS provider
   synthesizes via `/usr/bin/say` then converts with `/usr/bin/afconvert` using
   bounded argument arrays (never `shell=True`).
3. **Native voice-discovery race after multi-page shell load** — concurrent
   `say -v ?` probes could poison an empty voice cache. Discovery is now
   single-flight under a lock, does not permanently cache failed probes, and
   warms once when `SpeechService` starts. The browser cert runs the dedicated
   voice journey before the broader M64 shell regression.

## Browser certificate

Managed harness evidence:
`docs/evidence/m78/browser/M78_VOICE_BROWSER_CERT.json`

Result: **PASS**

- 33 hard gates
- 6 responsive gates
- 2 accessibility gates
- 4 security gates
- M64 shell regression retained (21 hard / 12 state / 6 responsive)
- zero page/console/framework-overlay errors recorded by the harness
- no tokens in voice URLs/responses; no private artifact paths leaked

## Backend/frontend verification

- Voice backend: 15 passed
- Frontend: 189 passed
- Voice + IELTS frontend contracts: passed
- `shell=True` scan on voice paths: clean
- public-listener scan on voice paths: clean
- production-code secret pattern scan on changed voice files: clean
- `git diff --check`: clean on mission changes

## Unchanged limitations (intentional)

- VoxCPM remains optional, disabled, not installed, not inference-verified, not
  quality-reviewed, and not certified.
- Nepali remains `UNSUPPORTED_NOT_VERIFIED`.
- Voice cloning remains `CAPABILITY_DISABLED`.
- Production activation is not authorized.
- No push, merge, deploy, credential, DNS, or Trading Guardian change.

## Change authority

Local commits only. Protected `docs/design-spec/` and pre-existing m25/m27/m28
evidence files were not staged.
