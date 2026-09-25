# SaathiOS Voice Setup Guide

Voice Settings is available at **Settings → Voice Settings**, or directly at `/settings/voice`. You can also find it from the command palette, the profile/mobile Settings surface, first-run onboarding, and the voice help link in Chat.

## Select and test a voice

1. Open **Settings → Voice Settings**.
2. Check **System voice status**. The voice and language counts are detected from the current browser; they are not hardcoded.
3. Leave **Enable voice output** on, choose a voice that the browser marks as local, then choose English, Nepali, or Mixed.
4. Choose **Play test**. **Stop test** cancels output, and **Replay last test** repeats the last selected phrase.
5. Adjust locale, rate, or volume if needed. These preferences are stored only in the browser profile.

The settings test excludes any voice the browser does not report as `localService=true`. If a saved voice disappears after an operating-system update, SaathiOS selects a deterministic local fallback and displays that change.

## English, Nepali, and mixed text

The English test is available when at least one local system voice is reported. Nepali audio is available only if the browser reports a local `ne-*` voice.

During the certification run, the in-app browser reported 180 local voices across 49 language tags and no local Nepali voice. SaathiOS therefore displays the Nepali phrase but refuses to claim or attempt native Nepali playback. Mixed text may be played by an English voice, but pronunciation quality is not certified by automation.

## Microphone permission and transcript preview

Voice Settings never starts the microphone on page load.

1. Enable **Voice input controls**.
2. Choose **Request microphone permission**. The permission probe immediately releases its media track; capture remains off.
3. Choose **Start microphone test** to begin browser recognition after an explicit user action.
4. Choose **Stop microphone test** to stop recognition and release acquired tracks.
5. Recognized text appears only in the in-memory transcript preview. If recognition is unavailable or denied, type in the same field to verify the text fallback.

The browser controls how its SpeechRecognition engine processes audio. SaathiOS does not send settings-test audio or transcripts to its API, but it cannot promise that a browser vendor performs speech recognition locally. Use the text fallback when strict local processing cannot be verified.

## Interruption behavior

- **Stop test** cancels browser and SaathiOS playback.
- Starting a microphone test first stops current output.
- The global voice runtime provides push-to-interrupt behavior.
- Full acoustic barge-in is not implemented and is not claimed.

Speech and microphone capture are cleaned up on explicit stop, route change, session-context change/logout, recognition end, and applicable errors. Starting a new test cancels the previous browser utterance so output does not overlap.

## Privacy

- No external voice provider, cloud speech account, API key, or provider credential is configured by Voice Settings.
- Settings-test audio and transcripts are not stored by SaathiOS and are not included in certification evidence.
- Persisted settings contain only enablement, a system voice identifier, locale, rate, volume, and the fixed interruption preference.
- Existing global Voice Runtime and Chat voice flows are different: they can submit recognized text to the loopback Saathi platform and may persist local sessions/transcripts. Voice Settings labels and tests its own isolated behavior separately.

## Troubleshooting

- **Voice count starts at zero:** wait briefly for the browser `voiceschanged` event. The page refreshes the list asynchronously.
- **Saved voice changed:** the operating system no longer reported that voice, so a local fallback was selected.
- **No Nepali voice:** install a compatible local Nepali system voice if one becomes available, restart the browser, and check the runtime status again. Do not assume installation support from this guide.
- **Permission denied:** enable microphone access in browser/site settings, reload Voice Settings, or use the text fallback.
- **Recognition unavailable:** use a supported browser or the text fallback. No cloud provider will be enabled automatically.
- **API unavailable:** the browser-only settings test still reports local capabilities; global Saathi speech services may show unavailable until the loopback platform API returns.

## Certification limit

Automated checks certify the rendered controls, state transitions, cleanup contracts, local-only request boundary, and truthful capability reporting. They do not certify audible quality. Status remains `OWNER_AUDIO_REVIEW_REQUIRED` until Ajay personally listens to the supported phrases and records the owner review.
