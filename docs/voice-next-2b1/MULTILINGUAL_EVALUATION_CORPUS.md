# MULTILINGUAL_EVALUATION_CORPUS

## Purpose

Bounded evaluation set for SaathiOS local STT qualification: English, Nepali, mixed, short interrupts, long turns, financial/SaathiOS terminology, noise, quiet room.

## Provenance

| Source | Role |
| --- | --- |
| Locally generated TTS (macOS `say` + edge-tts) | Automated WER/CER/latency/resource benches |
| Owner-recorded (OWNER_STT_QUALIFICATION.md) | Accent / live mic truth — **not auto-filled** |

Synthetic TTS is **not** a substitute for owner live qualification. It is sufficient to reject clearly unsuitable engines and measure resource/latency floors.

## Categories

| ID | Category | Count (min) |
| --- | --- | --- |
| EN_CMD | English commands | 8 |
| NE_CMD | Nepali commands | 6 |
| MIX | Mixed EN/NE | 8 |
| SHORT | Short interrupts | 4 |
| LONG | Long conversational | 3 |
| FIN | Financial terminology | 4 |
| SAATHI | SaathiOS-specific terms | 4 |
| NOISE | Background noise mix | 2 (generated with noise overlay) |
| QUIET | Quiet-room (clean TTS) | all clean variants |

## Reference utterances

### English commands

1. `Saathi, show my active missions.`
2. `Open the command center.`
3. `Stop.`
4. `Cancel that response.`
5. `Show portfolio risk.`
6. `What is Trading Guardian status?`
7. `Is ExecutionGateway healthy?`
8. `Compare today's NAV and drawdown.`

### Nepali commands

1. `मेरो आजको portfolio risk देखाऊ।`
2. `आजको market exposure कति छ?`
3. `मेरो pending approvals के छन्?`
4. `Trading Guardian को current status देखाऊ।`
5. `आजको NAV र drawdown compare गर।`
6. `कमान्ड सेन्टर खोल।`

### Mixed EN/NE

1. `Saathi, आजको portfolio मा सबैभन्दा ठूलो risk के हो?`
2. `Portfolio rebalance proposal देखाऊ।`
3. `ExecutionGateway healthy छ कि छैन?`
4. `Show my missions र approvals।`
5. `Cancel response र फेरि सुन।`
6. `Open command center र system health देखाऊ।`
7. `मेरो active missions list गर।`
8. `Drawdown कति छ today?`

### Short interrupts

1. `Stop.`
2. `Cancel.`
3. `Wait.`
4. `हजुर`

### Long conversational

1. `Can you explain the largest risk in my portfolio today and what I should review before any rebalance?`
2. `आजको बजारमा मेरो exposure कस्तो छ र कुन approval pending छ भनेर विस्तारमा भन्नुहोस्।`
3. `Saathi, summarize active missions, pending approvals, and Trading Guardian status in one short brief.`

### Financial / SaathiOS terms (overlap with above)

Target terms for preservation scoring:

```
Saathi, portfolio, risk, NAV, drawdown, rebalance, exposure,
Trading Guardian, ExecutionGateway, approvals, missions, command center
```

## Non-executable approval phrases

Corpus **must not** include phrases that auto-execute financial authority. Approvals remain review-only.

Forbidden as executable gold:

- Direct wire/transfer amounts with confirm tokens
- Live order placement language treated as authority

Allowed: `pending approvals`, status queries, risk views.

## File layout

```text
tools/voice-stt-bench/corpus/
  manifest.json
  wav/
    en_001.wav
    ne_001.wav
    ...
  transcripts/
    en_001.txt
```

## Generation script

`tools/voice-stt-bench/generate_corpus.py`

## Scoring notes

- English: WER primary
- Nepali / mixed: CER + human-readable comparison + intent preservation
- Do not collapse to one flattering average
