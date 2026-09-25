# RECORDING_GUIDE

## Audio target

| Property | Value |
| --- | --- |
| Channels | mono |
| Sample rate | 16 kHz |
| Format | PCM WAV (s16) |
| Compression | none on source |

## Tool

```bash
python3 tools/voice-stt-data/scripts/participant_recorder.py register \
  --speaker-id spk_001 --commercial --research --evaluation

python3 tools/voice-stt-data/scripts/participant_recorder.py record \
  --speaker-id spk_001 --seconds 5 --device mac_builtin --noise quiet

python3 tools/voice-stt-data/scripts/participant_recorder.py rerecord \
  --clip-id spk_001_mix_001_t01

python3 tools/voice-stt-data/scripts/participant_recorder.py status
```

## Variation (where practical)

- Mac / phone / headset mics
- Quiet / normal / moderate fan noise
- Distance and speaking rate variation
- Soft / normal / slightly faster speech

Do **not** intentionally create unsafe extreme volume.

## Privacy

- Local only; no auto-upload
- Pseudonyms only
- Withdraw via `withdrawal_reference` + speaker_id

