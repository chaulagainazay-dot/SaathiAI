# STT_ARCHITECTURE_DECISION

## Choice

```text
C. BROWSER STT REMAINS PRIMARY
```

## Rationale

- No UNIVERSAL_PRIMARY_QUALIFIED local model
- NE and MIX gates fail (best near-miss small CS)
- Owner intentional corpus incomplete
- Training-data license lineage unclear for Bijay13

## Hierarchy

```text
Browser SpeechRecognition (product primary)
        ↓
Manual text
```

Experimental: bijay-small-ne-en as ENGLISH_ONLY research path only (not product primary).

Language router: **not implemented**.

