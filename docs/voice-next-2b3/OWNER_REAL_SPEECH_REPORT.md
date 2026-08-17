# OWNER_REAL_SPEECH_REPORT

## Tool

`tools/voice-stt-bench/owner_record_tool.py`

- Local store: `~/.saathi/stt-owner-corpus/`
- Ratings template not auto-filled (`auto_filled: false`)
- ffmpeg avfoundation capture works on this host

## Coverage

| Required | Status |
| --- | --- |
| Tool built | YES |
| Mic path verified | YES (1 test capture) |
| Full intentional owner set (13 prompts) | **INCOMPLETE** (12 missing) |
| Owner subjective ratings | **NOT filled** (correct — not auto-filled) |

## Limitation

Automated 3s capture of `own_en_001` without human speech script cannot qualify accent. Full owner session remains a **major limitation**.

```text
OWNER_INTENTIONAL_CORPUS: PARTIAL_TOOL_ONLY
```

