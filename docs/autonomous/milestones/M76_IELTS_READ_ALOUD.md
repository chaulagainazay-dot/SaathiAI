# M76 — IELTSAlert Read-Aloud

## Result

`COMPLETE`

IELTSAlert feedback records now expose `Read aloud` through the shared M75
speech-output client and M74 backend service. No IELTS-specific provider,
playback controller, storage, queue, or authority was introduced.

## Delivered

- Read-aloud action only on persisted practice/submission records that contain
  backend feedback.
- Deterministic feedback-to-speech projection containing the feedback label,
  overall practice level or answer count, criterion levels/notes, limitations,
  and the explicit “never an official IELTS score” boundary.
- Learner response text is not repeated into synthesized feedback.
- Output is bounded to 4,000 characters before the backend independently
  validates it.
- Source metadata is `ielts_feedback`, language is `en-US`, and the
  provider-neutral `yeti_teacher` profile is selected.
- The global user speaking-rate preference remains authoritative because the
  request passes the bounded accessibility rate explicitly.
- Loading, synthesis, ready, Play, Stop, cancellation, provider unavailable,
  fallback, and failure states remain centralized in the shell.
- Browser `speechSynthesis` is not used, and no autoplay was added.

## Yeti posture

The Yeti Teacher is a conceptual provider-neutral profile:

> Warm, calm, encouraging adult teacher; clear international English; friendly
> and confident; medium-low pitch; natural conversational rhythm; moderately
> slow pace; precise pronunciation; gentle energy; never theatrical, robotic,
> childish, or overly dramatic.

The frontend refers only to `yeti_teacher`. Any future VoxCPM voice-design
prompt mapping remains private to the provider adapter. No real person,
reference recording, enrollment, or cloning is involved.

## Verification

```text
npm test
189 passed

npm run lint
passed with zero warnings

npm run build
compiled, lint/type validity, and 82 static routes passed
```

The added deterministic test proves that private learner response text is
excluded, feedback criteria are rendered readably, official-score claims remain
false, the 4,000-character ceiling holds, the Yeti profile is selected, and the
IELTS UI has no browser speech-synthesis path.

Evidence: `docs/evidence/m76/IELTS_READ_ALOUD_CERTIFICATION.json`.

## Remaining work

M77 runs live authenticated browser coverage for shell and IELTS speech,
unavailable/fallback/context/logout states, responsive/focus/error gates,
resource measurement, full backend/frontend regressions, dependency and secret
checks, and final autonomous closeout.
