# DATA_QA_REPORT

## Pipeline

`qa_clips.py` checks every clip for:

- file readable
- sample rate 16 kHz
- mono
- duration bounds
- RMS (reject near-silence)
- clipping fraction
- transcript present
- consent valid for bucket
- prompt_id known
- sha256 present

## Human transcript rule

Every train clip must eventually have `human_verified=true`.  
LLMs must **not** silently rewrite transcripts.

## Current run

Empty corpus — no clips QA'd.

```json
{
  "total": 0,
  "pass": 0,
  "status": "NO_MANIFEST"
}
```

QA tooling: **PASS** (unit tests green).  
Product corpus QA: **N/A (zero clips)**.

