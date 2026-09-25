# INSTALL_SECURITY_REPORT

## Isolation

```text
tools/voice-stt-bench/.venv-omni  (Python 3.12, not system site-packages)
```

## Dependencies installed (isolated)

- omnilingual-asr 0.1.0
- fairseq2 0.6 / fairseq2n
- torch 2.8.0 + torchaudio 2.8.0 (ABI matched after fix)
- libsndfile via Homebrew

## Security notes

| Issue | Status |
| --- | --- |
| `.pt` pickle checkpoint | Confirmed — not safetensors |
| Custom remote code | Official Meta package |
| Network on first load | Downloads model to `~/.cache/fairseq2/assets/` |
| Warnings suppressed | No |

## Install issues encountered

- Initial torchaudio 2.11 / torch 2.8 ABI mismatch → fixed by pin `torchaudio==2.8.0`

