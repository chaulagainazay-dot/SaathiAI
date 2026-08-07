# BARGE_IN_QUALITY_REPORT

## Classification path

```text
VAD speech → possible interruption → local/browser STT partial/final
  → meaningful? yes → REAL_INTERRUPTION
  → no / timeout → FALSE_INTERRUPTION
```

## Unit evidence

| Case | Result |
| --- | --- |
| Barge-in + no STT | FALSE after timeout |
| Barge-in + "Stop the response now" | REAL |
| Backchannel only | non-executable turn |

## Live rates

| Metric | Status |
| --- | --- |
| false interruption rate | UNMEASURED live (owner) |
| missed interruption rate | UNMEASURED live |
| resume behavior | input ownership preserved on ACOUSTIC_SPEECH |

## Claim limit

Do **not** claim adaptive conversational interruption.

